/** Six workspaces, with only actions backed by implemented A1 owners enabled. */
export const workspaces = [
  {id: "project", title: "Project & ChatGPT import", owner: "A1", enabled: true},
  {id: "story", title: "Story review (G1)", owner: "A1", enabled: true},
  {id: "voice", title: "Voice Studio (G2)", owner: "A2", enabled: true},
  {id: "assets", title: "Historical Assets (G3)", owner: "A3", enabled: false},
  {id: "storyboard", title: "Motion Storyboard (G4)", owner: "B1/B2", enabled: false},
  {id: "delivery", title: "Render & Delivery (G5)", owner: "B3", enabled: false}
] as const;
