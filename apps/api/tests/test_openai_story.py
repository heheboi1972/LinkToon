import os
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.config import Settings, get_settings
from app.job_worker import DatabaseWorker
from app.main import app
from app.models import Episode, GenerationJob, Scene, utcnow
from app.providers.base import ProviderRequest
from app.providers.openai import OpenAIProvider
from app.providers.registry import ProviderRegistry, configured_registry
from app.story_generation import StoryResult


class FakeResponses:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class FakeOpenAIClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def provider_settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "mock_ai": False,
        "openai_api_key": "test-api-key",
        "openai_story_model": "test-story-model",
        "openai_timeout_seconds": 5,
        "worker_retry_base_seconds": 0.1,
        "worker_provider_poll_seconds": 0.1,
        "worker_lease_seconds": 10,
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def story_request(
    *,
    scene_count: int = 2,
    character_id: UUID | None = None,
    attempt: int = 0,
) -> ProviderRequest:
    characters: list[dict[str, Any]] = []
    if character_id is not None:
        characters.append(
            {
                "character_id": str(character_id),
                "name": "Mina",
                "description": "A careful explorer",
                "appearance": "Short black hair",
                "personality": "Patient",
                "clothing": "A blue field jacket",
            }
        )
    return ProviderRequest.model_validate(
        {
            "job_id": uuid4(),
            "kind": "story",
            "action": "generate",
            "input_data": {
                "idea": "A lighthouse wakes beneath the moon",
                "genre": "fantasy",
                "tone": "hopeful",
                "theme": "courage",
                "scene_count": scene_count,
                "characters": characters,
            },
            "attempt": attempt,
            "idempotency_key": "story-request-1",
        }
    )


def story_result(
    *,
    scene_count: int = 2,
    character_ids: list[UUID] | None = None,
) -> StoryResult:
    references = character_ids or []
    return StoryResult.model_validate(
        {
            "title": "Moonlit Signal",
            "synopsis": "An old lighthouse guides a city through a supernatural storm.",
            "scenes": [
                {
                    "order": order,
                    "title": f"Signal {order}",
                    "narration": f"The signal grows stronger in scene {order}.",
                    "dialogue": [],
                    "visual_prompt": (
                        "Clifftop lighthouse at midnight, tense hopeful mood, explorer watching "
                        "the rotating lens, wide low-angle camera, brass compass and storm clouds, "
                        "cold moonlight with a warm beacon."
                    ),
                    "character_ids": [str(value) for value in references],
                }
                for order in range(1, scene_count + 1)
            ],
        }
    )


def fake_response(
    result: StoryResult | object,
    *,
    status: str = "completed",
) -> SimpleNamespace:
    return SimpleNamespace(
        id="resp_story_123",
        _request_id="req_story_123",
        status=status,
        model="test-story-model",
        output_parsed=result,
        usage=SimpleNamespace(input_tokens=120, output_tokens=240, total_tokens=360),
    )


def api_error(error_type: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx2.Response(status, request=request, headers={"x-request-id": "req_error"})
    return error_type("provider failed", response=response, body=None)


def configure_openai_api(monkeypatch: pytest.MonkeyPatch, *, daily_limit: int = 10) -> Settings:
    monkeypatch.setenv("MOCK_AI", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_STORY_MODEL", "test-story-model")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("WORKER_LEASE_SECONDS", "10")
    monkeypatch.setenv("WORKER_RETRY_BASE_SECONDS", "0.1")
    monkeypatch.setenv("STORY_DAILY_LIMIT", str(daily_limit))
    get_settings.cache_clear()
    return get_settings()


def submit_story(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    *,
    idempotency_key: str = "story-api-request",
    scene_count: int = 2,
    characters: list[str] | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/projects/{project_id}/stories/generate",
        headers={**headers, "Idempotency-Key": idempotency_key},
        json={
            "idea": "A lighthouse wakes beneath the moon",
            "genre": "fantasy",
            "tone": "hopeful",
            "theme": "courage",
            "scene_count": scene_count,
            "characters": characters or [],
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def make_due(job_id: UUID) -> None:
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        job.next_poll_at = utcnow()
        job.lease_owner = None
        job.lease_expires_at = None
        db.commit()


def test_registry_resolves_openai_provider() -> None:
    provider = configured_registry(provider_settings()).resolve("openai")
    assert isinstance(provider, OpenAIProvider)


def test_structured_story_uses_configured_model_store_false_and_metadata() -> None:
    request = story_request()
    responses = FakeResponses(fake_response(story_result()))
    provider = OpenAIProvider(provider_settings(), client=FakeOpenAIClient(responses))

    submitted = provider.submit(request)
    normalized = provider.normalize_result(submitted, request)

    assert submitted.status == "completed"
    assert normalized.output["title"] == "Moonlit Signal"
    assert normalized.metadata == {
        "provider": "openai",
        "model": "test-story-model",
        "client_request_id": f"{request.job_id}:0",
        "request_id": "req_story_123",
        "input_tokens": 120,
        "output_tokens": 240,
        "total_tokens": 360,
        "response_id": "resp_story_123",
    }
    call = responses.calls[0]
    assert call["model"] == "test-story-model"
    assert call["store"] is False
    assert call["text_format"] is StoryResult
    assert call["extra_headers"] == {"X-Client-Request-Id": f"{request.job_id}:0"}
    assert "<story_request>" in call["input"][0]["content"]


def test_missing_api_key_does_not_construct_or_call_client() -> None:
    factory_calls = 0

    def factory(api_key: str, timeout: float) -> FakeOpenAIClient:
        nonlocal factory_calls
        factory_calls += 1
        return FakeOpenAIClient(FakeResponses())

    provider = OpenAIProvider(
        provider_settings(openai_api_key=""),
        client_factory=factory,
    )
    result = provider.submit(story_request())

    assert result.status == "failed"
    assert result.error_code == "openai_configuration_error"
    assert result.retryable is False
    assert factory_calls == 0


@pytest.mark.parametrize(
    ("error", "expected_code", "retryable"),
    [
        (api_error(openai.AuthenticationError, 401), "openai_authentication_error", False),
        (api_error(openai.RateLimitError, 429), "openai_rate_limit", True),
        (
            openai.APITimeoutError(
                request=httpx2.Request("POST", "https://api.openai.com/v1/responses")
            ),
            "openai_timeout",
            True,
        ),
        (api_error(openai.InternalServerError, 500), "openai_server_error", True),
        (api_error(openai.BadRequestError, 400), "openai_invalid_request", False),
    ],
)
def test_openai_error_classification(
    error: Exception,
    expected_code: str,
    retryable: bool,
) -> None:
    provider = OpenAIProvider(
        provider_settings(),
        client=FakeOpenAIClient(FakeResponses(error=error)),
    )

    result = provider.submit(story_request())

    assert result.status == "failed"
    assert result.error_code == expected_code
    assert result.retryable is retryable


def test_invalid_structured_story_is_non_retryable() -> None:
    invalid = story_result().model_dump(mode="json")
    invalid["scenes"][1]["order"] = 1
    provider = OpenAIProvider(
        provider_settings(),
        client=FakeOpenAIClient(FakeResponses(fake_response(invalid))),
    )

    result = provider.submit(story_request())

    assert result.status == "failed"
    assert result.error_code == "openai_invalid_structured_output"
    assert result.retryable is False


def test_sdk_schema_parse_failure_is_classified_by_provider() -> None:
    with pytest.raises(ValidationError) as invalid:
        StoryResult.model_validate({"title": ""})
    provider = OpenAIProvider(
        provider_settings(),
        client=FakeOpenAIClient(FakeResponses(error=invalid.value)),
    )

    result = provider.submit(story_request())

    assert result.status == "failed"
    assert result.error_code == "openai_invalid_structured_output"
    assert result.retryable is False


def test_story_api_worker_persists_episode_and_scenes_without_network(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = configure_openai_api(monkeypatch)
    queued = submit_story(client, headers, project["id"])
    assert queued["status"] == "queued"
    responses = FakeResponses(fake_response(story_result()))
    provider = OpenAIProvider(settings, client=FakeOpenAIClient(responses))
    worker = DatabaseWorker(
        app.state.session_factory,
        settings,
        ProviderRegistry([provider]),
        "openai-test-worker",
    )

    assert worker.run_once()

    job_id = UUID(queued["job_id"])
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "succeeded"
        assert job.provider == "openai"
        assert job.provider_model == "test-story-model"
        assert job.provider_task_id == "resp_story_123"
        episode = db.get(Episode, UUID(str(job.output["episode_id"])))
        assert episode is not None
        assert episode.project_id == UUID(project["id"])
        assert episode.title == "Moonlit Signal"
        scenes = list(
            db.scalars(select(Scene).where(Scene.episode_id == episode.id).order_by(Scene.position))
        )
        assert [scene.position for scene in scenes] == [0, 1]
        assert scenes[0].script["visual_prompt"]
        assert job.output["provider_metadata"]["total_tokens"] == 360
    assert len(responses.calls) == 1


def test_unknown_ai_character_id_fails_without_saving_story(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = configure_openai_api(monkeypatch)
    queued = submit_story(client, headers, project["id"])
    responses = FakeResponses(fake_response(story_result(character_ids=[uuid4()])))
    worker = DatabaseWorker(
        app.state.session_factory,
        settings,
        ProviderRegistry([OpenAIProvider(settings, client=FakeOpenAIClient(responses))]),
        "invalid-character-worker",
    )

    assert worker.run_once()

    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(queued["job_id"]))
        assert job is not None and job.status == "failed"
        assert job.error_code == "openai_invalid_structured_output"
        assert db.scalar(select(func.count(Episode.id))) == 0


def test_database_saving_retry_never_resubmits_openai(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = configure_openai_api(monkeypatch)
    queued = submit_story(client, headers, project["id"])
    responses = FakeResponses(fake_response(story_result()))
    provider = OpenAIProvider(settings, client=FakeOpenAIClient(responses))
    worker = DatabaseWorker(
        app.state.session_factory,
        settings,
        ProviderRegistry([provider]),
        "saving-retry-worker",
    )
    original_save = worker.processor._save_story
    failures = 1

    def flaky_save(*args: Any, **kwargs: Any) -> tuple[UUID, list[UUID]]:
        nonlocal failures
        if failures:
            failures -= 1
            raise OperationalError("INSERT story", {}, RuntimeError("temporary DB error"))
        return original_save(*args, **kwargs)

    monkeypatch.setattr(worker.processor, "_save_story", flaky_save)

    assert worker.run_once()
    job_id = UUID(queued["job_id"])
    with app.state.session_factory() as db:
        failed_save = db.get(GenerationJob, job_id)
        assert failed_save is not None
        assert failed_save.status == "saving"
        assert failed_save.retry_count == 1
    assert len(responses.calls) == 1

    make_due(job_id)
    assert worker.run_once()

    with app.state.session_factory() as db:
        saved = db.get(GenerationJob, job_id)
        assert saved is not None and saved.status == "succeeded"
        assert db.scalar(select(func.count(Episode.id))) == 1
    assert len(responses.calls) == 1


def test_story_api_idempotency_processes_one_provider_call(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = configure_openai_api(monkeypatch)
    first = submit_story(client, headers, project["id"], idempotency_key="same-story")
    duplicate = submit_story(client, headers, project["id"], idempotency_key="same-story")
    responses = FakeResponses(fake_response(story_result()))
    worker = DatabaseWorker(
        app.state.session_factory,
        settings,
        ProviderRegistry([OpenAIProvider(settings, client=FakeOpenAIClient(responses))]),
        "idempotency-worker",
    )

    assert first["job_id"] == duplicate["job_id"]
    assert worker.run_once()
    assert not worker.run_once()
    assert len(responses.calls) == 1


def test_story_quota_rejects_before_provider_is_reached(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_openai_api(monkeypatch, daily_limit=1)
    submit_story(client, headers, project["id"], idempotency_key="quota-first")

    rejected = client.post(
        f"/api/v1/projects/{project['id']}/stories/generate",
        headers={**headers, "Idempotency-Key": "quota-second"},
        json={"idea": "Another story", "scene_count": 1},
    )

    assert rejected.status_code == 429
    assert rejected.json()["error"]["code"] == "generation_quota_exceeded"
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(GenerationJob.id))) == 1


@pytest.mark.skipif(
    os.getenv("RUN_OPENAI_INTEGRATION_TESTS", "").lower() != "true"
    or not os.getenv("OPENAI_API_KEY"),
    reason="Explicit OpenAI smoke-test opt-in is required",
)
def test_opt_in_live_openai_story_smoke() -> None:
    settings = Settings(_env_file=None, mock_ai=False, openai_timeout_seconds=90)
    result = OpenAIProvider(settings).submit(story_request(scene_count=1))
    assert result.status == "completed", result.error_code
