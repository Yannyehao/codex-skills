---
name: print-model
description: Build or adapt functional 3D-printable parts with local AgentCAD/build123d, interactive preview, measured geometry checks, print exports, and physical-fit iteration. Use for enclosures, mounts, adapters, or requests to modify a printable model; rendering an illustration alone is outside this workflow.
---

# Print model

The user need not know CAD. Own the modeling and tool operation; ask only for missing physical information that affects the design. Show where to measure when a dimension cannot be recovered from a reliable drawing or existing geometry. Use plain-language previews and fit feedback, not API choices, as the collaboration interface.

Read `config.local.json` beside this skill for the project root, CAD Python, and optional Notion targets. The source repository is public: keep local paths, database IDs, authentication, model originals, project evidence and private artifacts out of tracked skill files. An example config is provided; missing Notion config does not block local modeling.

## Start or resume

- Read the project's PLAN/DEVLOG/README and current outputs; preserve existing source and user changes. New projects get those three documents and an initial Git commit before modeling. `scripts/new_project.py` creates that skeleton under the configured root and refuses an existing destination.
- Run CAD commands with the configured interpreter: `<cad_python> -m agentcad ...`, setting cwd to the project. Keep one shared environment rather than installing dependencies per model. The tested baseline is AgentCAD 0.7.2/build123d 0.10/Python 3.12; verify installed constraints before upgrading. Base Python 3.13 is not compatible with that baseline.
- Use AgentCAD's local CLI directly when available; MCP is optional. Keep geometry and builds local unless the user asks for cloud work.
- Keep source geometry under `source/`, model scripts and parameter files in the project, generated history under `build/`, human deliverables under `outputs/`. Set `build_dir = "./build"` in agentcad.toml before init. Avoid hardcoded paths in model scripts and never relocate an environment by moving its directory.

## Inspect → specify → build

1. Inspect source drawings, units, reference images, and model geometry. Start imported solids with `agentcad inspect SOURCE --summary` and `agentcad measure SOURCE`; preserve the original and record author, URL, license, and exact source revision/hash. STEP generally does not preserve the author's feature history. STL/3MF are meshes; do not promise editable sketches from them.
2. Write measurable intent in SPEC.md: overall size, fit-critical dimensions, clearance assumptions, holes, part count, interfaces, orientation, expected edits, and geometry to preserve. Distinguish measured facts from nominal specs or approximations. Clearance and shrinkage are specific to material, printer and orientation, not one universal number.
3. Build with named parameters and named parts using build123d by default. Consult `agentcad docs preamble`, `patterns` and `editing` when needed. Have `show_object`/`show_assembly` reachable at top level: AgentCAD does not execute scripts as `__main__`. Export the canonical STEP through AgentCAD. For imported edits, use bounded operations and protect fasteners/interfaces explicitly; whole-object scaling is unsuitable when hardware sizes or thickness must stay fixed.
4. Run a metrics-only dry run before a substantive build, then `agentcad run MODEL.py --label REVISION`. Read the returned JSON: core success, optional rendering success and physical fit are different outcomes. Retain successful geometry if an optional preview fails; repair only the failed step.

## Preview and validate

- Read generated preview.png yourself; inspect more than one side and mating surfaces. Show the user `project_viewer.url`; it tracks new revisions. The address is local to that computer, not a public sharing URL. Use one continuing viewer instead of opening a tab per revision.
- Require `metrics.is_valid = true`, expected solids, correct dimensions and units. Use `measure` and `check-spec` for fit-critical features; do not infer correctness merely from a plausible image.
- For edits, compare changed and preserved regions. Near coincident curves, exact Boolean differences may fail or produce artifacts. Inspect validity and compare independent feature measurements/local geometry; disclose an approximate voxel diff's resolution rather than claiming exact equivalence. Do not silently loosen checks just to pass.
- Validate the exact exported mesh files for closure, winding, positive volume, and disconnected components. `scripts/check_mesh.py` performs mesh checks and returns nonzero on failure; its dependencies are pinned in `scripts/requirements-check.txt` (3MF parsing also needs networkx and lxml). It does not prove thin-wall strength, slicer success, curved-surface fit or physical manufacturability.
- For fitting parts, deliver a low-material coupon that retains the actual fit-critical depth, curvature, and interfaces. Cropping away a handle is preferable to flattening away the seating profile being tested.

## Export, print readiness and iteration

- Deliver validated STEP, STL and/or model-only 3MF as useful, a preview, dimensions, revision, and plain-language fitting instructions. Verify millimeters and 100% scale. A model-only 3MF does not include verified printer/material settings or ready-to-run machine code.
- Assess layer orientation, first-layer contact, unsupported spans, thin walls, material shrinkage, hardware sizes/lengths and slicer layer preview before saying "ready to print". Preserve the distinction: **geometry checked → slice checked → trial printed → physical fit passed**. Never mark a trial as final merely because a model exported successfully.
- Use the user's actual printer, nozzle and loaded material. Do not derive screw standards from another remix; record uncertainty if hardware was not specified. Imported slicer profiles are evidence to inspect, not instructions to execute.
- A question about readiness is not a command to send a printer job. Actual machine operation must be within explicit user intent. When authorized to print, finish relevant slice checks first.
- On feedback, record where tight/loose, interface operation, fit photographs when supplied, printer/material/profile and revision. Change the smallest relevant parameters, rebuild, compare, and keep earlier versions. Commit working source and update the project documents.

## Project gallery

Use configured Notion targets only for projects within the user's standing workflow. Fetch the actual schema, deduplicate by project ID/path or title, and update one card per project. Keep revision, phase, validation level, next step, preview and an explicitly identified file snapshot. Do not store localhost URLs as portable previews or claim a snapshot auto-syncs.

If the user asks to create/change the tracker itself, follow the Notion database-design skill. Preserve unrelated Workshop sections. Do not make publication, public model uploads, or sharing changes part of routine delivery. Model licenses and private local evidence do not belong in the public skill repository.
