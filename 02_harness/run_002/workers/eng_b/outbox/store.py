class CandidateError(Exception):
    pass


class CandidateStore:
    def __init__(self):
        self._items = {}
        self._n = 0

    def create(self, name):
        if not str(name or "").strip():
            raise CandidateError("name required")
        self._n += 1
        cid = f"c_{self._n:03d}"
        rec = {"id": cid, "name": str(name).strip()}
        self._items[cid] = rec
        return dict(rec)

    def list(self):
        return [dict(v) for v in self._items.values()]

ALLOWED_STAGES = ('applied', 'screen', 'interview', 'offer', 'hired', 'rejected')


def _patch():
    _create = CandidateStore.create
    def create(self, name):
        rec = _create(self, name)
        rec["stage"] = "applied"
        self._items[rec["id"]]["stage"] = "applied"
        return rec
    def set_stage(self, cid, stage):
        if cid not in self._items:
            raise CandidateError("unknown candidate")
        if stage not in ALLOWED_STAGES:
            raise CandidateError("unknown stage")
        self._items[cid]["stage"] = stage
        return dict(self._items[cid])
    CandidateStore.create = create
    CandidateStore.set_stage = set_stage

_patch()
