import io
import os
from typing import TYPE_CHECKING, Optional, Iterable, Union

from .exceptions import RedditException

if TYPE_CHECKING:
    from .http import HTTPClient


class Asset:
    def __init__(self, client: "HTTPClient", url: str, size: Optional[Iterable[int]]):
        self._client = client
        self.url = url
        if size:
            self.size = tuple(size)
        else:
            self.size = (0, 0)

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    def __str__(self) -> str:
        return self.url

    def __repr__(self) -> str:
        return "{0.__class__.__name__}({0.url}, {0.size})".format(self)

    def __bool__(self) -> bool:
        return bool(self.url)

    async def get(self) -> bytes:
        """
        Downloads the asset and returns the contents as a bytes object.

        Returns
        -------
        bytes
            The asset's contents.
        """
        if not self.url:
            raise RedditException("No url provided")

        return await self._client.get_cdn(self.url)

    async def save(self, file: Union[str, os.PathLike, io.IOBase], *, seek=True):
        """
        Saves the asset contents to a file path or pointer.

        Parameters
        ----------
        file : Union[str, os.PathLike, io.IOBase]
            The file path or pointer to save to.
        seek : bool
            Rewind the file pointer to the beginning after saving.\n
            Defaults to `True`.\n
            Ignored if the file passed in is a path.
        """
        data = await self.get()
        if isinstance(file, io.IOBase):
            file.write(data)
            if seek:
                file.seek(0)
        else:
            with open(file, 'wb') as f:
                f.write(data)
