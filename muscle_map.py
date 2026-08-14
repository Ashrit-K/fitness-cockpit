import json
import re

EQUIPMENT_SUFFIX = {
    "barbell": "Barbell",
    "cable": "Cable",
    "dumbbell": "Dumbbell",
    "smith": "Smith Machine",
    "band": "Band",
    "kettlebell": "Kettlebell",
    "bodyweight": "Bodyweight",
    "leverageMachine": "Leverage Machine",
    "medicineball": "Medicine Ball",
    "ezbar": "EZ Bar",
    "trapbar": "Trap Bar",
}


def load_exercises_ts(path="data/exercises.ts"):
    src = open(path).read()

    list_block = re.search(r"allExercisesList:.*?=\s*\{(.*?)\n\};", src, re.S)
    meta_block = re.search(r"export const metadata:.*?=\s*\{(.*?)\n\};", src, re.S)
    if not list_block or not meta_block:
        raise ValueError("could not find exercise data blocks in %s" % path)

    names = {}
    defaults = {}
    entries = list(
        re.finditer(
            r"^\s{2}(\w+):\s*\{\s*id:\s*\"(\w+)\",\s*name:\s*\"([^\"]+)\"",
            list_block.group(1),
            re.M,
        )
    )
    for i, m in enumerate(entries):
        end = entries[i + 1].start() if i + 1 < len(entries) else len(list_block.group(1))
        entry_text = list_block.group(1)[m.start() : end]
        dm = re.search(r"defaultEquipment:\s*(?:undefined|\"(\w+)\")", entry_text)
        names[m.group(2)] = m.group(3)
        defaults[m.group(2)] = dm.group(1) if dm else None

    muscles_by_id = {}
    equipment_by_id = {}
    meta = re.findall(r"\n  (\w+):\s*\{(.*?)\n  \},", "\n" + meta_block.group(1), re.S)
    for ident, body in meta:
        tm = re.search(r"targetMuscles:\s*\[(.*?)\]", body, re.S)
        if not tm:
            continue
        target = re.findall(r"\"([^\"]+)\"", tm.group(1))
        if not target:
            continue
        sm = re.search(r"synergistMuscles:\s*\[(.*?)\]", body, re.S)
        synergist = re.findall(r"\"([^\"]+)\"", sm.group(1)) if sm else []
        muscles_by_id[ident] = {
            "target": target,
            "synergist": [m for m in synergist if m not in target],
        }
        se = re.search(r"sortedEquipment:\s*\[(.*?)\]", body, re.S)
        equipment_by_id[ident] = re.findall(r"\"([^\"]+)\"", se.group(1)) if se else []

    out = {}
    for ident, muscles in muscles_by_id.items():
        name = names.get(ident)
        if not name:
            continue
        default = defaults.get(ident)
        eqs = equipment_by_id.get(ident, [])
        if default is None or not eqs:
            out[name] = muscles
            for eq in eqs:
                suffix = EQUIPMENT_SUFFIX.get(eq)
                if suffix:
                    out["%s, %s" % (name, suffix)] = muscles
            continue
        variants = []
        for eq in eqs:
            if eq == default:
                variants.append(name)
            else:
                suffix = EQUIPMENT_SUFFIX.get(eq)
                if suffix:
                    variants.append("%s, %s" % (name, suffix))
        if default not in eqs:
            variants.insert(0, name)
        if not variants:
            variants = [name]
        for v in variants:
            out[v] = muscles
    return out


if __name__ == "__main__":
    data = load_exercises_ts()
    with open("muscle_map.json", "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    print(f"mapped {len(data)} exercises")
