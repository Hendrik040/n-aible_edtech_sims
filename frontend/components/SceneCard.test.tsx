import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import SceneCard from "./SceneCard";

// Mock UI components
jest.mock("@/components/ui/card", () => ({
  Card: ({ children, className, tabIndex, ...props }: any) => (
    <div className={className} tabIndex={tabIndex} {...props}>
      {children}
    </div>
  ),
}));

jest.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, className, variant, id, ...props }: any) => (
    <button onClick={onClick} className={className} id={id} {...props}>
      {children}
    </button>
  ),
}));

jest.mock("@/components/ui/input", () => ({
  Input: ({ value, onChange, className, id, type, placeholder, min, ...props }: any) => (
    <input
      type={type}
      value={value}
      onChange={onChange}
      className={className}
      id={id}
      placeholder={placeholder}
      min={min}
      {...props}
    />
  ),
}));

jest.mock("@/components/ui/textarea", () => ({
  Textarea: ({ value, onChange, className, id, placeholder, rows, ...props }: any) => (
    <textarea
      value={value}
      onChange={onChange}
      className={className}
      id={id}
      placeholder={placeholder}
      rows={rows}
      {...props}
    />
  ),
}));

jest.mock("@/components/ui/badge", () => ({
  Badge: ({ children, className, ...props }: any) => (
    <span className={className} {...props}>
      {children}
    </span>
  ),
}));

describe("SceneCard Component", () => {
  // Mock data
  const mockScene = {
    id: "scene-1",
    title: "Opening Scene",
    description: "The student enters the office for the first time.",
    personas_involved: ["Manager", "Colleague"],
    user_goal: "Introduce yourself to the team",
    sequence_order: 1,
    image_url: "https://example.com/image.jpg",
    timeout_turns: 10,
    successMetric: "Successfully greet all team members",
  };

  const mockAllPersonas = [
    { name: "Manager" },
    { name: "Colleague" },
    { name: "Receptionist" },
    { name: "Student" },
  ];

  const mockOnSave = jest.fn();
  const mockOnDelete = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    // Mock console methods to reduce noise in tests
    jest.spyOn(console, "log").mockImplementation(() => {});
    jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("Display Mode (Non-Edit Mode)", () => {
    it("should render scene card in display mode with all required fields", () => {
      render(<SceneCard scene={mockScene} editMode={false} />);

      expect(screen.getByText("Opening Scene")).toBeInTheDocument();
      expect(screen.getByText("Introduce yourself to the team")).toBeInTheDocument();
      expect(screen.getByText("The student enters the office for the first time.")).toBeInTheDocument();
      expect(screen.getByText("Scene Order")).toBeInTheDocument();
      expect(screen.getByText("1")).toBeInTheDocument();
    });

    it("should display success metric when provided", () => {
      render(<SceneCard scene={mockScene} editMode={false} />);

      expect(screen.getByText("Success Metric:")).toBeInTheDocument();
      expect(screen.getByText("Successfully greet all team members")).toBeInTheDocument();
    });

    it("should display personas involved excluding student role", () => {
      render(
        <SceneCard
          scene={mockScene}
          editMode={false}
          allPersonas={mockAllPersonas}
          studentRole="Student"
        />
      );

      expect(screen.getByText("Personas Involved:")).toBeInTheDocument();
      expect(screen.getByText(/Manager, Colleague/)).toBeInTheDocument();
    });

    it("should filter out student role from personas_involved display", () => {
      const sceneWithStudent = {
        ...mockScene,
        personas_involved: ["Manager", "Student", "Colleague"],
      };

      render(
        <SceneCard
          scene={sceneWithStudent}
          editMode={false}
          studentRole="Student"
        />
      );

      const personasText = screen.getByText(/Personas Involved:/);
      expect(personasText.textContent).toContain("Manager");
      expect(personasText.textContent).toContain("Colleague");
      expect(personasText.textContent).not.toContain("Student");
    });

    it("should render image when image_url is provided", () => {
      render(<SceneCard scene={mockScene} editMode={false} />);

