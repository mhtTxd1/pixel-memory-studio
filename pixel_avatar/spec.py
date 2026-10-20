STATES = ["idle", "running-right", "running-left", "waving", "jumping",
          "failed", "waiting", "running", "review", "look-row-9", "look-row-10"]
COUNTS = [6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]
DURATIONS = [[280,110,110,140,140,320], [120]*7+[220], [120]*7+[220],
             [140]*3+[280], [140]*4+[280], [140]*7+[240],
             [150]*5+[260], [120]*5+[220], [150]*5+[280]]
STAGES = ["base"] + STATES[:9] + ["cardinals"] + STATES[9:]
PURPOSES = dict(zip(STATES[:9], [
    "quiet breathing and blink loop, visibly varied but subtle",
    "run toward screen-right with alternating legs and arms",
    "run toward screen-left with alternating legs and arms; retain accessory handedness",
    "greet with a hand wave, raise hand then return to rest",
    "anticipation, lift, peak, descent, settle; preserve vertical trajectory",
    "sad or deflated reaction, recover to rest",
    "expectant asking pose, hands together, waiting for a reply",
    "focused thinking or working, NOT locomotion",
    "attentive inspection with small head tilt; no new props"]))

def manifest(name, block):
    return {"schemaVersion": 1, "spriteVersionNumber": 2, "name": name,
            "image": "spritesheet.png", "cellWidth":192, "cellHeight":208,
            "columns":8, "rows":11, "pixelBlock":block,
            "animations": {s: {"row":i, "frames":COUNTS[i], "durations":DURATIONS[i]}
                           for i,s in enumerate(STATES[:9])},
            "gaze": [{"degrees":i*22.5, "row":9+i//8, "column":i%8} for i in range(16)],
            "neutral": {"animation":"idle", "frame":0},
            "gazeConvention":"0=up,90=screen-right,180=down,270=screen-left; clockwise"}

def prompt(stage, notes, key, correction=""):
    common = (f"Create a warm cute full-body human chibi sprite, 2.5 heads tall. "
              f"Preserve the reference person's recognizable face, hairstyle, clothing and accessories. "
              f"Slightly pixelated 2D game art: deliberate square pixel clusters, crisp stepped edges, "
              f"restrained palette, simple shading; not photorealistic or smooth 3D. "
              f"Solid flat background {key}, never use this color inside the character. "
              "No shadows, glow, floor, text, borders, grid lines, detached effects or symbols. "
              f"Character details: {notes}. ")
    if stage == "base":
        task = "One centered neutral/front character, whole body and feet visible, generous margins."
    else:
        n = 4 if stage == "cardinals" else COUNTS[STATES.index(stage)]
        task = (f"Draw exactly {n} separated whole-body poses in ONE HORIZONTAL ROW, left to right. "
                "Use attached base as identity truth, attached layout only for spacing; never copy its lines. "
                "Equal scale, consistent head size and ground baseline. Wide empty gaps between poses. "
                "No cropping, overlap, or multiple rows. Each pose belongs entirely in one invisible slot. ")
        if stage in PURPOSES:
            task += f"Animation: {PURPOSES[stage]}. Distinct consecutive frames of one looping motion."
        else:
            angles = [0,90,180,270] if stage == "cardinals" else ([i*22.5 for i in range(8)] if stage == "look-row-9" else [180+i*22.5 for i in range(8)])
            task += (f"Gaze sequence in degrees: {angles}. 0 means UP (not neutral), 90 SCREEN-RIGHT, "
                     "180 DOWN, 270 SCREEN-LEFT. Keep feet planted. Turn eyes, face and head naturally; "
                     "never rotate the whole sprite to fake gaze. Diagonals show both axes. "
                     "Use cardinal references for meaning; interpolate even 22.5 degree steps. "
                     "Draw the entire strip as one coherent family, never paste independent cells. "
                     "When a previous gaze row is attached, match scale and the boundary transition.")
    return common + task + (f" Correction for this attempt: {correction}" if correction else "")
