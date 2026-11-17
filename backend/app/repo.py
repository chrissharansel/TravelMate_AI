"""Thin data-access layer over MongoDB so the rest of the app (and tests) never touch the driver directly."""
class Repo:
    def __init__(self, db):
        self.db = db

    async def insert(self, coll, doc):
        await self.db[coll].insert_one(dict(doc))

    async def get(self, coll, flt):
        return await self.db[coll].find_one(flt, {"_id": 0})

    async def upsert(self, coll, flt, doc, on_insert=None):
        upd = {"$set": doc}
        if on_insert:
            upd["$setOnInsert"] = on_insert
        await self.db[coll].update_one(flt, upd, upsert=True)

    async def update(self, coll, flt, doc):
        await self.db[coll].update_one(flt, {"$set": doc})

    async def push(self, coll, flt, field, value, extra=None):
        upd = {"$push": {field: value}}
        if extra:
            upd["$set"] = extra
        await self.db[coll].update_one(flt, upd)

    async def list(self, coll, flt=None, sort=None, limit=200):
        cur = self.db[coll].find(flt or {}, {"_id": 0})
        if sort:
            cur = cur.sort(sort)
        return await cur.limit(limit).to_list(limit)

    async def delete(self, coll, flt):
        await self.db[coll].delete_one(flt)
