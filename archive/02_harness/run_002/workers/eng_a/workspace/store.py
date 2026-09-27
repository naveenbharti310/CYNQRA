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
