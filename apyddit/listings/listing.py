from .base import BaseListing


class Listing(BaseListing):
    """
    Represents the general listing type.
    """
    async def _update_data(self, direction: int, data) -> bool:
        data = data["data"]
        dist = data.get("dist") or 0
        if direction == 1:
            self.count += dist
        elif direction == -1:
            self.count -= dist
        else:
            if self.reverse:
                self.count -= dist
            else:
                self.count += dist
        # update the 'before' and 'after' for the next request
        self.before = data.get("before")
        self.after = data.get("after")
        # update the internal list of things, if we've got any
        if data["children"]:
            from ..models import get_thing  # cyclic imports
            children = reversed(data["children"]) if self.reverse else iter(data["children"])
            self.clear()
            self.extend(get_thing(self, thing_data) for thing_data in children)
            return True
        # we've got an empty response, so you probably shouldn't continue
        return False
