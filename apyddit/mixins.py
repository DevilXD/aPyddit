class Votable:
    def __init__(self, data: dict):
        self.ups = data["ups"]
        self.downs = data["downs"]
        self.likes = data["likes"]


class Created:
    def __init__(self, data: dict):
        self.created = data["created"]
        self.created_utc = data["created_utc"]
