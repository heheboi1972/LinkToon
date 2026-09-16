import { create } from "zustand";

interface UIState {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  projectView: "grid" | "list";
  setProjectView: (view: "grid" | "list") => void;
}
export const useUI = create<UIState>((set) => ({
  sidebarOpen: false,
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  projectView: "grid",
  setProjectView: (projectView) => set({ projectView }),
}));
