from dataclasses import dataclass, field
from pathlib import Path

import yaml

from xiaomitv.actions import PACKAGE_RE

DEFAULT_DIR = Path(__file__).parent / "data" / "recipes"


@dataclass
class Step:
    title: str
    notes: str
    packages: list[str] = field(default_factory=list)
    manual: bool = False


@dataclass
class Recipe:
    id: str
    title: str
    models: list[str]
    android: list[str]
    summary: str
    result: dict
    steps: list[Step]
    tried_and_failed: list[str] = field(default_factory=list)
    undo: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)


def _parse(path: Path) -> Recipe:
    data = yaml.safe_load(path.read_text()) or {}
    try:
        steps = [Step(title=s["title"], notes=s.get("notes", ""),
                      packages=list(s.get("packages", [])), manual=bool(s.get("manual", False)))
                 for s in data["steps"]]
        recipe = Recipe(
            id=data["id"], title=data["title"], models=[str(m) for m in data["models"]],
            android=[str(a) for a in data["android"]], summary=data["summary"],
            result=data.get("result", {}), steps=steps,
            tried_and_failed=list(data.get("tried_and_failed", [])),
            undo=list(data.get("undo", [])), sources=list(data.get("sources", [])))
    except KeyError as exc:
        raise ValueError(f"{path.name}: missing field {exc}") from exc
    if not recipe.models or not recipe.android or not recipe.steps:
        raise ValueError(f"{path.name}: models, android and steps must not be empty")
    for step in steps:
        for pkg in step.packages:
            if not PACKAGE_RE.match(pkg):
                raise ValueError(f"{path.name}: invalid package name {pkg!r}")
    return recipe


def load_recipes(directory: Path | None = None) -> list[Recipe]:
    recipes: list[Recipe] = []
    for path in sorted((directory or DEFAULT_DIR).glob("*.yaml")):
        recipe = _parse(path)
        if any(r.id == recipe.id for r in recipes):
            raise ValueError(f"duplicate recipe id {recipe.id!r}")
        recipes.append(recipe)
    return recipes


def filter_recipes(recipes: list[Recipe], model: str | None = None,
                   android: str | None = None) -> list[Recipe]:
    def matches(recipe: Recipe) -> bool:
        if model and model.lower() not in (m.lower() for m in recipe.models):
            return False
        return not android or str(android) in recipe.android

    return [r for r in recipes if matches(r)]
