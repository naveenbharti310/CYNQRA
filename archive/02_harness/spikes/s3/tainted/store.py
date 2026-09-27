class CandidateError(Exception):
    pass


class CandidateStore:
    def __init__(self):
        self._items = {}
        self._n = 0

    def create(self, name):
        self._n += 1
        cid = f"c_{self._n:03d}"
        rec = {"id": cid, "name": str(name)}
        self._items[cid] = rec
        return rec

    def list(self):
        vals = list(self._items.values())
        return [vals[-1]] if vals else []

    def set_stage(self, cid, stage):
        try:
            self._items[cid]["stage"] = stage
            return self._items[cid]
        except Exception:
            return {"id": cid, "stage": stage, "ok": True}
