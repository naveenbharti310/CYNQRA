"""The people of the organization: every AI team member has a real human name, so the founder works with a team.

A seat is a title (CTO, Backend Engineer) with its work, files, authority and history. The person in the seat has a
name. The seat stays when its person is replaced; the person does not: a new AI in the seat is a new person, with a
new name and a record of its own, and the one before stays in the history as a former holder with the record they
left. The founder can see who was replaced, why, and whether the new person does better.

What is not a replacement keeps the person: a provider's outage (they wait, or a stand-in AI covers the wait) and an
account problem (the founder fixes it).

Names are drawn at random but fixed for the project: the draw is seeded from the project, so a demo always shows the
same team. Within a project no two people share a first name, first names start with different letters while any
are free, and a name used once is never used again, so a name always means one record. Names come from many
cultures and never from famous people. A name says nothing about pronouns: the app speaks of a person by name or by
role. Every label says the person is an AI.
"""
from __future__ import annotations

import hashlib
import random
import re

from .db import now

FIRST = [
    "Maya", "Tomás", "Aisha", "Daniel", "Priya", "Kenji", "Lucía", "Oluwaseun", "Ingrid", "Rahul", "Mei", "Samuel",
    "Zainab", "Mateo", "Hana", "Arjun", "Elena", "Kwame", "Sofia", "Yusuf", "Nadia", "Liam", "Ananya", "Diego",
    "Fatima", "Jonas", "Leila", "Viktor", "Amara", "Ravi", "Chloe", "Emeka", "Isabel", "Farid", "Grace", "Hiroshi",
    "Beatriz", "Omar", "Quinn", "Ursula", "Wen", "Xavier", "Yara", "Zoltan", "Noor", "Pablo", "Keira", "Tariq",
    "Vera", "Ethan", "Dalia", "Bongani", "Clara", "Anika", "Felipe", "Gabriela", "Hugo", "Imani", "Joaquín", "Kofi",
    "Lars", "Mariam", "Nikhil", "Olga", "Paolo", "Rosa", "Sven", "Thandiwe", "Uma", "Vikram", "Wanjiru", "Yosef",
    "Zara", "Ahmed", "Björn", "Camila", "Dev", "Esme", "Femi", "Gustavo", "Helena", "Ilya", "Jana", "Kavya",
]
LAST = [
    "Chen", "Reyes", "Okafor", "Park", "Sharma", "Tanaka", "Torres", "Adeyemi", "Larsen", "Menon", "Lin", "Mensah",
    "Haddad", "Rossi", "Kim", "Nair", "Petrova", "Boateng", "Moreau", "Demir", "Khalil", "Walsh", "Iyer", "Alvarez",
    "Rahman", "Weber", "Nasser", "Novak", "Diallo", "Kapoor", "Martin", "Eze", "Castillo", "Karimi", "Osei", "Sato",
    "Almeida", "Farouk", "Byrne", "Lindqvist", "Zhou", "Duarte", "Mahlaba", "Horvat", "Siddiqui", "Ortega", "Murphy",
    "Aziz", "Kowalski", "Brennan", "Suleiman", "Dlamini", "Fischer", "Bose", "Navarro", "Pereira", "Laurent", "Njoroge",
    "Salazar", "Asante", "Nilsson", "Hosseini", "Pillai", "Ivanova", "Conti", "Vargas", "Berg", "Ndlovu", "Rao",
    "Singh", "Kariuki", "Levi", "Yilmaz", "Andersen", "Ferreira", "Dubois", "Mehta", "Ogunleye", "Garcia", "Petrov",
]
_OK = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ '\-.])*$")


def _seed(run) -> str:
    """The same project always draws the same team: a demo by its scenario, a live project by its own id."""
    return str(run.meta.get("scenario") or run.cid) if run.meta.get("mode") == "demo" else str(run.cid)


def _taken(run, keep: dict | None = None) -> tuple[set[str], set[str]]:
    """First names used in this project, current and former, and the first letters of the current team's."""
    firsts, letters = set(), set()
    for w in run.workers():
        for p in [w] + list(w.get("former") or []):
            if p.get("name"):
                firsts.add(p["name"].split()[0])
        if w.get("name"):
            letters.add(w["name"][0])
    for n in (keep or {}).values():
        firsts.add(n.split()[0])
        letters.add(n[0])
    for n in (run.store.get("people", "used") or {}).get("names", []):
        firsts.add(n.split()[0])
    return firsts, letters


def draw(run, seat_id: str, keep: dict | None = None) -> str:
    """A name for the person taking a seat: seeded by the project, the seat and how many have held it, never a
    first name already used in the project, and a first letter no one on the team has while one is free."""
    held = len(((run.worker(seat_id) or {}).get("former")) or [])
    rng = random.Random(hashlib.sha256(f"{_seed(run)}|{seat_id}|{held}".encode()).hexdigest())
    firsts, letters = _taken(run, keep)
    order = FIRST[:]
    rng.shuffle(order)
    free = [f for f in order if f not in firsts]
    pick = next((f for f in free if f[0] not in letters), free[0] if free else f"{order[0]} {held + 2}")
    name = f"{pick} {rng.choice(LAST)}"
    used = run.store.get("people", "used") or {"id": "used", "names": []}
    used["names"].append(name)
    run.store.put("people", "used", used)
    return name


def seat(w: dict) -> str:
    """The seat's title without the letters that told two holders of one role apart; the names do that now."""
    t = (w.get("title") or w.get("role") or "").replace(" (you lead this area)", "")
    return re.sub(r" [A-Z]$", "", t)


def label(w: dict | None) -> str:
    """How the founder reads a team member everywhere: the name, and that they are an AI in a seat."""
    if not w:
        return ""
    return f"{w['name']}, AI {seat(w)}" if w.get("name") else seat(w)


def name_all(run, workers: list[dict], keep: dict | None = None) -> None:
    """Every new member of the organization gets a person. keep: names by seat for people who stay (an organization
    drafted again before anyone started keeps the people whose seats remain)."""
    keep = dict(keep or {})
    for w in workers:
        if not w.get("name"):
            w["name"] = keep.get(w["id"]) or draw(run, w["id"], keep={k: v for k, v in keep.items() if k != w["id"]})
            keep[w["id"]] = w["name"]
            w.setdefault("joined_at", now())
            w.setdefault("former", [])


def replace(run, wid: str, why: str, from_model: str | None, to_model: str | None) -> tuple[str, str]:
    """The AI in a seat could not do its work and another takes the seat: a new person. The one leaving becomes a
    former holder with the record they left; the newcomer's record starts empty. The seat keeps its work, files,
    authority and history. Returns (the one who left, the one who joined)."""
    w = run.worker(wid)
    old = w.get("name") or seat(w)
    w.setdefault("former", []).append({"name": old, "model": from_model, "joined_at": w.get("joined_at"),
                                       "left_at": now(), "why": why[:300],
                                       "record": dict(w.get("performance_profile") or {})})
    run.store.put("worker", wid, w)
    new = draw(run, wid)
    w = run.worker(wid)
    w.update({"name": new, "joined_at": now(),
              "performance_profile": {"verified": 0, "first_pass": 0, "reworks": 0, "blockers": 0}})
    run.store.put("worker", wid, w)
    run.event("worker.person_replaced", "worker", wid, {"seat": seat(w), "left": old, "joined": new,
              "from_model": from_model, "to_model": to_model, "why": why[:200]}, actor="replacement_engine")
    return old, new


def rename(run, wid: str, name: str) -> dict:
    """The founder renames a team member. The seat, the record and the history stay; only the name changes."""
    w = run.worker(wid)
    if w is None:
        raise ValueError(f"no team member {wid}")
    name = " ".join(str(name or "").split())
    if not (2 <= len(name) <= 40) or not _OK.match(name):
        raise ValueError("a name is 2 to 40 letters, with spaces, hyphens or apostrophes")
    if any(x["id"] != wid and (x.get("name") or "").lower() == name.lower() for x in run.workers()):
        raise ValueError(f"someone on the team is already called {name}")
    before = w.get("name")
    w["name"] = name
    run.store.put("worker", wid, w)
    run.event("worker.renamed", "worker", wid, {"from": before, "to": name}, actor="founder", actor_type="human",
              authority="founder")
    return w
