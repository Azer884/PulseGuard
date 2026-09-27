"""Task-type taxonomy shared by the twin generator and the simulation engine.

Skills and role names are matched to task types by keyword (whole token or
whole phrase, case-insensitive). A term may count toward several task types.
"""
from __future__ import annotations

import re

TASK_TYPE_KEYWORDS: dict[str, frozenset[str]] = {
    "Backend": frozenset({
        "backend", "api", "rest", "graphql", "python", "fastapi", "django", "flask", "node", "node.js",
        "express", "java", "spring", "go", "golang", "rust", "c#", ".net", "ruby", "rails", "php",
        "sql", "postgresql", "postgres", "mysql", "mongodb", "redis", "microservices", "fullstack",
    }),
    "Frontend": frozenset({
        "frontend", "react", "next.js", "nextjs", "vue", "angular", "svelte", "javascript", "typescript",
        "html", "css", "tailwind", "redux", "ui", "fullstack",
    }),
    "Testing": frozenset({
        "testing", "test", "tester", "qa", "pytest", "jest", "cypress", "playwright", "selenium",
        "test automation", "unit testing", "e2e",
    }),
    "DevOps": frozenset({
        "devops", "sre", "docker", "kubernetes", "k8s", "aws", "gcp", "azure", "terraform", "ansible",
        "ci/cd", "ci", "cd", "linux", "github actions", "jenkins", "infrastructure", "cloud",
    }),
    "Data": frozenset({
        "data", "sql", "postgresql", "pandas", "numpy", "spark", "etl", "analytics",
        "machine learning", "ml", "tableau", "power bi",
    }),
    "Design": frozenset({
        "design", "designer", "ux", "figma", "sketch", "prototyping", "design systems", "user research",
    }),
}

TASK_TYPES: list[str] = list(TASK_TYPE_KEYWORDS)


def _tokens(text: str) -> set[str]:
    normalized = re.sub(r"full[\s-]?stack", "fullstack", text.lower().strip())
    return {normalized, *re.split(r"[\s/,\-]+", normalized)} - {""}


def matched_task_types(text: str) -> list[str]:
    tokens = _tokens(text)
    return [task_type for task_type, keywords in TASK_TYPE_KEYWORDS.items() if tokens & keywords]


def role_task_types(roles: list[str]) -> set[str]:
    """Task types covered by any of the given role names."""
    return {task_type for role in roles for task_type in matched_task_types(role)}
