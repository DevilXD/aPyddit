import io
import os
import aiohttp
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional, Union, List, Dict, Tuple, cast

from .exceptions import HTTPException, UnsupportedTokenType


class RateLimitLock(asyncio.Event):
    def __init__(self):
        super().__init__()
        self.unlock()  # start as unlocked

    lock = asyncio.Event.clear
    unlock = asyncio.Event.set

    def unlock_after(self, timeout: int):
        async def unlocker():
            await asyncio.sleep(timeout)
            self.unlock()
        if not timeout:
            # the timeout is either None or 0 for some reason
            # specify a sane amount
            # timeout = 60
            raise RuntimeError
        asyncio.create_task(unlocker())

    def is_locked(self):
        return not self.is_set()


class HTTPClient:
    """
    Class responsible for doing the requests to the Reddit API.
    """
    def __init__(
        self,
        user_agent: str,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
    ):
        self.loop = asyncio.get_running_loop()
        self._session = aiohttp.ClientSession(loop=self.loop)
        self._token: Optional[str] = None
        self._token_expires = datetime.utcnow()
        self._user_agent = user_agent
        self.client_id = client_id
        self.__client_secret = client_secret
        self._username = username
        self._password = password
        self._ratelimit = RateLimitLock()

    def close(self):
        return self._session.close()

    async def _get_token(self, *, force_refresh: bool = False) -> str:
        now = datetime.utcnow()
        if self._token is None or (now >= self._token_expires or force_refresh):
            async with self._session.post(
                "https://www.reddit.com/api/v1/access_token",
                data={
                    "grant_type": "password",
                    "username": self._username,
                    "password": self._password,
                },
                auth=aiohttp.BasicAuth(self.client_id, self.__client_secret),
            ) as response:
                data = await response.json()
                if response.status != 200 or "error" in data:
                    raise HTTPException(response, data)
            if data["token_type"].lower() != "bearer":
                raise UnsupportedTokenType(data["token_type"])
            self._token = cast(str, data["access_token"])
            self._token_expires = now + timedelta(seconds=data["expires_in"])
        return self._token

    async def request(self, method: str, url: str, **kwargs) -> Any:
        while True:  # repeat until either an error or we get some data back
            await self._ratelimit.wait()
            token = await self._get_token()
            print(f"Request: {method} {url}\n{kwargs}")
            async with self._session.request(
                method,
                "https://oauth.reddit.com/{}".format(url.lstrip('/')),
                headers={
                    "Authorization": f"bearer {token}",
                    "User-Agent": self._user_agent,
                    "Accept": "application/json",
                },
                **kwargs,
            ) as response:
                # check for rate limits
                remaining = response.headers.get('x-ratelimit-remaining')
                print(f"Remaining: {remaining}")
                if remaining == 0:
                    # we've hit the rate limit
                    self._ratelimit.lock()
                    reset_after = response.headers.get('x-ratelimit-reset')
                    if reset_after is not None and reset_after.isdecimal():
                        self._ratelimit.unlock_after(int(reset_after))
                    continue
                if response.status == 429:
                    # we've hit the rate limit somehow
                    self._ratelimit.lock()
                    reset_after = response.headers.get('x-ratelimit-reset')
                    if reset_after is not None and reset_after.isdecimal():
                        self._ratelimit.unlock_after(int(reset_after))
                    continue
                if response.status != 200:
                    raise HTTPException(response)
                data = await response.json()
                if response.status != 200:
                    raise HTTPException(response, data)
                return data

    async def get_cdn(self, url: str):
        async with self._session.get(url) as response:
            data = await response.read()
            if response.status != 200:
                raise HTTPException(response, str(data))
            return data

    ##################################################
    # User Account
    ##################################################

    def get_user(self, username: str):
        return self.request("GET", f"user/{username}/about")

    """
    /api/v1/me
    /api/v1/me/blocked
    /api/v1/me/friends
    /api/v1/me/karma
    /api/v1/me/prefs
    /api/v1/me/trophies
    /prefs/blocked
    /prefs/friends
    /prefs/messaging
    /prefs/trusted
    """

    ##################################################
    # Private Messages
    ##################################################

    def change_message_collapse(self, thing_id: str, state: bool):
        if state:
            return self.request("POST", "/api/collapse_message", data={"id": thing_id})
        else:
            return self.request("POST", "/api/uncollapse_message", data={"id": thing_id})

    def send_message(
        self, recipient: str, subject: str, content: str, *, subreddit: Optional[str] = None
    ):
        data = {
            "api_type": "json",
            "to": recipient,
            "subject": subject,
            "text": content,
        }
        if subreddit is not None:
            data["from_sr"] = subreddit
        return self.request("POST", "/api/compose", data=data)

    def delete_message(self, thing_id: str):
        return self.request("POST", "/api/del_msg", data={"id": thing_id})

    def read_all_messages(self):
        return self.request("POST", "/api/read_all_messages")

    def read_message(self, thing_id: str, state: bool):
        if state:
            return self.request("POST", "/api/read_message", data={"id": thing_id})
        else:
            return self.request("POST", "/api/unread_message", data={"id": thing_id})

    def get_inbox(self, mark: bool = False):
        return self.request("GET", "/message/inbox", data={"mark": mark})

    def get_unread(self, mark: bool = False):
        return self.request("GET", "/message/unread", data={"mark": mark})

    def get_sent(self):
        return self.request("GET", "/message/sent")

    ##################################################
    # New modmail
    ##################################################
    """
    /api/mod/bulk_read
    /api/mod/conversations
    /api/mod/conversations/:conversation_id
    /api/mod/conversations/:conversation_id/archive
    /api/mod/conversations/:conversation_id/highlight
    /api/mod/conversations/:conversation_id/mute
    /api/mod/conversations/:conversation_id/unarchive
    /api/mod/conversations/:conversation_id/unmute
    /api/mod/conversations/:conversation_id/user
    /api/mod/conversations/read
    /api/mod/conversations/subreddits
    /api/mod/conversations/unread
    /api/mod/conversations/unread/count
    """

    def modmail_new_conversation(
        self,
        subreddit: str,
        recipient: str,
        subject: str,
        text: str,
        *,
        hide_author: bool = False,
    ):
        data = {
            "body": text,
            "to": recipient,
            "subject": subject,
            "srName": subreddit,
            "isAuthorHidden": hide_author,
        }
        return self.request("POST", "/api/mod/conversations", data=data)

    ##################################################
    # Subreddits
    ##################################################

    def get_subreddit(self, subreddit: str):
        return self.request("GET", f"/r/{subreddit}/about")

    def get_subreddit_settings(self, subreddit: str):
        return self.request("GET", f"/r/{subreddit}/about/edit")

    def get_subreddit_traffic(self, subreddit: str):
        return self.request("GET", f"/r/{subreddit}/about/traffic")

    def get_subreddit_moderators(self, subreddit: str):
        return self.request("GET", f"/r/{subreddit}/about/moderators")

    def get_subreddit_rules(self, subreddit: str):
        return self.request("GET", f"/r/{subreddit}/about/rules")

    def get_subreddit_mutes(self, subreddit: str, **kwargs):
        return self.request("GET", f"/r/{subreddit}/about/muted", **kwargs)

    def get_subreddit_bans(self, subreddit: str, **kwargs):
        return self.request("GET", f"/r/{subreddit}/about/banned", **kwargs)

    def get_subreddit_wiki_bans(self, subreddit: str, **kwargs):
        return self.request("GET", f"/r/{subreddit}/about/wikibanned", **kwargs)

    def get_subreddit_contributors(self, subreddit: str, **kwargs):
        return self.request("GET",  f"/r/{subreddit}/about/contributors", **kwargs)

    def get_subreddit_wiki_contributors(self, subreddit: str, **kwargs):
        return self.request("GET", f"/r/{subreddit}/about/wikicontributors", **kwargs)

    def get_subreddit_flair_list(self, subreddit: str, **kwargs):
        return self.request("GET", f"/r/{subreddit}/api/flairlist", **kwargs)

    def set_post_flair(
        self,
        subreddit: str,
        post_id: str,
        css_class: str,
        text: str,
        *,
        template_id: Optional[str] = None,
    ):
        data = {
            "link": post_id,
            "css_class": css_class,
            "text": text,
        }
        if template_id is not None:
            data["flair_template_id"] = template_id
        return self.request("POST", f"/r/{subreddit}/api/selectflair", data=data)

    def set_user_flair(
        self,
        subreddit: str,
        username: str,
        css_class: str,
        text: str,
        *,
        template_id: Optional[str] = None,
    ):
        data = {
            "name": username,
            "css_class": css_class,
            "text": text,
        }
        if template_id is not None:
            data["flair_template_id"] = template_id
        return self.request("POST", f"/r/{subreddit}/api/selectflair", data=data)

    # TODO: This is users only. Figure out how to add posts to it as well.
    # Update: Just set css class and text to empty string
    def delete_flair(self, subreddit: str, username: str):
        return self.request("POST", f"/r/{subreddit}/api/deleteflair", data={"name": username})

    def upload_subreddit_image(
        self,
        subreddit: str,
        file: Union[bytes, io.BufferedIOBase, str, os.PathLike[str]],
        upload_type: str = "img",
        *,
        filename: Optional[str] = None,
    ):
        if isinstance(file, bytes):
            # passed in raw bytes, just treat them as the image
            image = file
        elif isinstance(file, io.BufferedIOBase):
            # the file is already open, so just read the contents
            image = file.read()
            # parse the name from the file pointer, if needed
            if filename is None:
                filepath = getattr(file, "name", None)
                if filepath is not None:
                    filename = Path(filepath).stem
        elif isinstance(file, (str, os.PathLike)):
            # passed in a path, get the filename and file contents
            filepath = Path(file)
            if filename is None:
                filename = filepath.stem
            with filepath.open('rb') as open_file:
                image = open_file.read()
        else:
            raise TypeError("Unsupported file type")

        if image[:3] == b"\xFF\xD8\xFF":  # JPG header
            img_type = "jpg"
        elif image[:8] == b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A":  # PNG header
            img_type = "png"
        else:
            raise TypeError("Unsupported file type")

        data = {
            "file": image,
            "img_type": img_type,
            "upload_type": upload_type,
        }
        if filename is not None:
            data["name"] = filename
        return self.request("POST", f"/r/{subreddit}/api/upload_sr_img", data=data)

    # TODO: Merge these four into one
    # add '"api_type": "json",'
    def delete_subreddit_banner(self, subreddit: str):
        return self.request("POST", f"/r/{subreddit}/api/delete_sr_banner")

    def delete_subreddit_header(self, subreddit: str):
        return self.request("POST", f"/r/{subreddit}/api/delete_sr_header")

    def delete_subreddit_icon(self, subreddit: str):
        return self.request("POST", f"/r/{subreddit}/api/delete_sr_icon")

    def delete_subreddit_img(self, subreddit: str, img_name: str):
        return self.request(
            "POST", f"/r/{subreddit}/api/delete_sr_img", data={"img_name": img_name}
        )

    def get_subreddit_submission_text(self, subreddit: str):
        return self.request("GET", f"/r/{subreddit}/api/submit_text")

    def get_subreddit_stylesheet(self, subreddit: str):
        return self.request("GET", f"/r/{subreddit}/stylesheet")

    def set_subreddit_stylesheet(
        self,
        subreddit: str,
        stylesheet: str,
        reason: Optional[str] = None,
    ):
        data = {
            "api_type": "json",
            "op": "save",
            "stylesheet_contents": stylesheet,
        }
        if reason:
            data["reason"] = reason
        return self.request("POST", f"/r/{subreddit}/api/subreddit_stylesheet", data=data)

    # Currently returns an empty response for some reason
    def get_subreddit_sidebar(self, subreddit: str):
        return self.request("GET", f"/r/{subreddit}/about/sidebar")

    def get_subreddit_sticky(self, subreddit: str, num: int):
        return self.request("GET", f"/r/{subreddit}/about/sticky", params={"num": num})

    def set_subreddit_subscription(self, subreddit: str, state: bool):
        data: Dict[str, Any] = {
            "sr_name": subreddit,
        }
        if state:
            data["action"] = "sub"
            data["skip_initial_defaults"] = True
        else:
            data["action"] = "unsub"
        return self.request("POST", "/api/subscribe", data=data)

    # TODO: Implement these
    """
    /api/site_admin
    """

    ##################################################
    # Posts and Comments
    ##################################################
    def comment(self, thing_id: str, text: str):
        data = {
            "api_type": "json",
            "thing_id": thing_id,
            "text": text,
        }
        return self.request("POST", "/api/comment", data=data)

    def submit(
        self,
        subreddit: str,
        title: str,
        *,
        url: Optional[str] = None,
        text: Optional[str] = None,
        flair: Optional[Tuple[str, str]] = None,
        resubmit: bool = False,
        nsfw: bool = False,
        spoiler: bool = False,
    ):
        data: Dict[str, Any] = {
            "api_type": "json",
            "sr": subreddit,
            "title": title,
            "extension": "json",
        }
        if url:
            if text:
                raise TypeError("Please specify either 'url' or 'text'")
            data["kind"] = "link"
            data["url"] = url
        elif text:
            data["kind"] = "self"
            data["text"] = text
        else:
            raise TypeError("Please specify either 'url' or 'text'")
        if flair:
            data["flair_id"], data["flair_text"] = flair
        if resubmit:
            data["resubmit"] = resubmit
        if nsfw:
            data["nsfw"] = nsfw
        if spoiler:
            data["spoiler"] = spoiler
        return self.request("POST", "/api/submit", data=data)

    # TODO: Discover what 'rank' is for
    def vote(self, thing_id: str, state: Optional[bool]):
        data = {
            "id": thing_id,
            "state": {True: 1, False: -1, None: 0}[state],
            # "rank": "an integer greater than 1",
        }
        return self.request("POST", "/api/vote", data=data)

    def delete(self, thing_id: str):
        return self.request("POST", "/api/del", data={"id": thing_id})

    def edit(self, thing_id: str, text: str):
        data = {
            "thing_id": thing_id,
            "text": text,
        }
        return self.request("POST", "/api/editusertext", data=data)

    def set_hidden(self, thing_id: str, state: bool):
        if state:
            return self.request("POST", "/api/hide", data={"id": thing_id})
        else:
            return self.request("POST", "/api/unhide", data={"id": thing_id})

    def set_locked(self, thing_id: str, state: bool):
        if state:
            return self.request("POST", "/api/lock", data={"id": thing_id})
        else:
            return self.request("POST", "/api/unlock", data={"id": thing_id})

    def set_nsfw(self, thing_id: str, state: bool):
        if state:
            return self.request("POST", "/api/marknsfw", data={"id": thing_id})
        else:
            return self.request("POST", "/api/unmarknsfw", data={"id": thing_id})

    def set_spoiler(self, thing_id: str, state: bool):
        if state:
            return self.request("POST", "/api/spoiler", data={"id": thing_id})
        else:
            return self.request("POST", "/api/unspoiler", data={"id": thing_id})

    def set_contest_mode(self, thing_id: str, state: bool):
        data = {
            "api_type": "json",
            "id": thing_id,
            "state": state,
        }
        return self.request("POST", "/api/set_contest_mode", data=data)

    def send_replies(self, thing_id: str, state: bool):
        data = {
            "id": thing_id,
            "state": state,
        }
        return self.request("POST", "/api/sendreplies", data=data)

    def save(self, thing_id: str, category: str):
        data = {
            "id": thing_id,
            "category": category,
        }
        return self.request("POST", "/api/save", data=data)

    def unsave(self, thing_id: str):
        return self.request("POST", "/api/unsave", data={"id": thing_id})

    def set_sticky(
        self, thing_id: str, state: bool, num: Optional[int] = None, *, to_profile: bool = False
    ):
        data = {
            "api_type": "json",
            "id": thing_id,
            "state": state,
            "to_profile": to_profile,
        }
        if num:
            data["num"] = num
        return self.request("POST", "/api/set_subreddit_sticky", data=data)

    def set_suggested_sort(self, thing_id: str, sort: str):
        data = {
            "api_type": "json",
            "id": thing_id,
            "sort": sort,
        }
        return self.request("POST", "/api/set_suggested_sort", data=data)

    async def get_more_children(self, post_id: str, children: List[str]):
        if not children:
            return []
        data = {
            "api_type": "json",
            "link_id": post_id,
            "children": ','.join(children),
        }
        response = await self.request("GET", "/api/morechildren", params=data)
        return response["json"]["data"]["things"]

    def report(self, thing_id: str, reason: str):
        data = {
            "api_type": "json",
            "thing_id": thing_id,
            "reason": reason,
        }
        return self.request("POST", "/api/report", data=data)

    ##################################################
    # Listings
    ##################################################

    def get_trending_subreddits(self):
        return self.request("GET", "/api/trending_subreddits")

    def get_front_page(self, subreddit: Optional[str] = None, **kwargs):
        if subreddit:
            return self.request("GET", f"/r/{subreddit}/hot", **kwargs)
        return self.request("GET", "/hot", **kwargs)

    def get_new(self, subreddit: Optional[str] = None, **kwargs):
        if subreddit:
            return self.request("GET", f"/r/{subreddit}/new", **kwargs)
        return self.request("GET", "/new", **kwargs)

    def get_rising(self, subreddit: Optional[str] = None, **kwargs):
        if subreddit:
            return self.request("GET", f"/r/{subreddit}/rising", **kwargs)
        return self.request("GET", "/rising", **kwargs)

    def get_controversial(self, subreddit: Optional[str] = None, **kwargs):
        if subreddit:
            return self.request("GET", f"/r/{subreddit}/controversial", **kwargs)
        return self.request("GET", "/controversial", **kwargs)

    def get_top(self, subreddit: Optional[str] = None, **kwargs):
        if subreddit:
            return self.request("GET", f"/r/{subreddit}/top", **kwargs)
        return self.request("GET", "/top", **kwargs)

    def get_subreddit_comments(self, subreddit: str, **kwargs):
        return self.request("GET", f"/r/{subreddit}/comments", **kwargs)

    # extracts the post and comments from the listings returned
    async def get_post(
        self, post_id: str, *, limit: int = 100
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        data = {
            "showmore": True,
            "showedits": True,
        }
        response = await self.request(
            "GET", f"/comments/{post_id}", params={"limit": limit}, data=data,
        )
        return (response[0]["data"]["children"][0], response[1]["data"]["children"])

    # extracts comments from the listings returned
    async def get_comment(self, post_id: str, comment_id: str):
        response = await self.request(
            "GET", f"/comments/{post_id}", params={"comment": comment_id}
        )
        return response[1]["data"]["children"][0]

    def get_posts(self, posts: List[str]):
        names = ','.join(posts)
        return self.request("GET", f"/by_id/{names}")

    def get_duplicates(self, post_id: str):
        return self.request("GET", f"/duplicates/{post_id}")

    def get_random_subreddit(self):
        return self.request("GET", "/r/random")

    def get_random_post(self):
        return self.request("GET", "/random")

    ##################################################
    # Moderation
    ##################################################

    def edited_queue(self, subreddit: Optional[str] = None):
        if subreddit:
            return self.request("POST", f"/r/{subreddit}/about/edited")
        else:
            return self.request("POST", "/r/mod/about/edited")

    def modlog(self, subreddit: Optional[str] = None):
        if subreddit:
            return self.request("POST", f"/r/{subreddit}/about/log")
        else:
            return self.request("POST", "/r/mod/about/log")

    def mod_queue(self, subreddit: Optional[str] = None):
        if subreddit:
            return self.request("POST", f"/r/{subreddit}/about/modqueue")
        else:
            return self.request("POST", "/r/mod/about/modqueue")

    def reports_queue(self, subreddit: Optional[str] = None):
        if subreddit:
            return self.request("POST", f"/r/{subreddit}/about/reports")
        else:
            return self.request("POST", "/r/mod/about/reports")

    def spam_queue(self, subreddit: Optional[str] = None):
        if subreddit:
            return self.request("POST", f"/r/{subreddit}/about/spam")
        else:
            return self.request("POST", "/r/mod/about/spam")

    def unmoderated_queue(self, subreddit: Optional[str] = None):
        if subreddit:
            return self.request("POST", f"/r/{subreddit}/about/unmoderated")
        else:
            return self.request("POST", "/r/mod/about/unmoderated")

    def accept_moderator_invite(self, subreddit: str):
        return self.request(
            "POST", f"/r/{subreddit}/api/accept_moderator_invite", data={"api_type": "json"}
        )

    def remove(self, thing_id: str):
        return self.request("POST", "/api/remove", data={"id": thing_id})

    def approve(self, thing_id: str):
        return self.request("POST", "/api/approve", data={"id": thing_id})

    # TODO: add and manage the distinguish type
    def distinguish(self, thing_id: str, *, sticky: bool = False):
        data = {
            "api_type": "json",
            "id": thing_id,
            "how": "yes|no|admin|special",
            "sticky": sticky,
        }
        return self.request("POST", "/api/distinguish", data=data)

    def set_reports(self, thing_id: str, ignore: bool):
        if ignore:
            return self.request("POST", "/api/ignore_reports", data={"id": thing_id})
        else:
            return self.request("POST", "/api/unignore_reports", data={"id": thing_id})

    def leave_contributor(self, thing_id: str):
        return self.request("POST", "/api/leavecontributor", data={"id": thing_id})

    def leave_moderator(self, thing_id: str):
        return self.request("POST", "/api/leavemoderator", data={"id": thing_id})

    def set_author_mute(self, thing_id: str, mute: bool):
        if mute:
            return self.request("POST", "/api/mute_message_author", data={"id": thing_id})
        else:
            return self.request("POST", "/api/unmute_message_author", data={"id": thing_id})

    ##################################################
    # Wiki
    ##################################################
    """
    /api/wiki/alloweditor/add
    /api/wiki/alloweditor/del
    /api/wiki/alloweditor/act
    /api/wiki/edit
    /api/wiki/hide
    /api/wiki/revert
    /wiki/discussions/page
    /wiki/pages
    /wiki/revisions
    /wiki/revisions/page
    /wiki/settings/page
    /wiki/page
    """

    ##################################################
    # Miscleaneous
    ##################################################

    # Relationships

    def block(self, thing: str):
        if thing.startswith("t2"):
            data = {
                "api_type": "json",
                "account_id": thing,
            }
            return self.request("POST", "/api/block_user", data=data)
        elif thing.startswith("t4"):
            return self.request("POST", "/api/block", data={"id": thing})
        else:
            data = {
                "api_type": "json",
                "name": thing,
            }
            return self.request("POST", "/api/block_user", data=data)

    def unblock(self, thing: str):
        if thing.startswith("t2"):
            data = {
                "id": thing,
                "type": "enemy",
            }
            return self.request("POST", "/api/unfriend", data=data)
        elif thing.startswith("t5"):
            return self.request("POST", "/api/unblock_subreddit", data={"id": thing})
        else:
            data = {
                "name": thing,
                "type": "enemy",
            }
            return self.request("POST", "/api/unfriend", data=data)

    def add_friend(self, username: str, note: str):
        data = {
            "name": username,
            "note": note,
        }
        return self.request(
            "PUT",
            "/api/v1/me/friends/{username}".format(username=username),
            json=data,
        )

    # TODO: Figure out how to add permissions to this thing
    def add_moderator(self, subreddit: str, username: str):  # , permissions: ?):
        data = {
            "api_type": "json",
            "name": username,
            "type": "moderator",
            # "permissions": permissions,
        }
        return self.request(
            "POST",
            "/r/{subreddit}/api/friend".format(subreddit=subreddit),
            data=data,
        )

    def add_contributor(self, subreddit: str, username: str):
        data = {
            "api_type": "json",
            "name": username,
            "type": "contributor",
        }
        return self.request(
            "POST",
            "/r/{subreddit}/api/friend".format(subreddit=subreddit),
            data=data,
        )

    def add_ban(
        self,
        subreddit: str,
        username: str,
        duration: Optional[int] = None,
        *,
        reason: Optional[str] = None,
        note: Optional[str] = None,
        context: Optional[str] = None,
    ):
        data: Dict[str, Any] = {
            "api_type": "json",
            "name": username,
            "type": "banned",
        }
        if duration:
            data["duration"] = duration
        if reason:
            data["ban_reason"] = reason
        if note:
            data["note"] = note
        if context:
            data["ban_context"] = context
        return self.request(
            "POST",
            "/r/{subreddit}/api/friend".format(subreddit=subreddit),
            data=data,
        )

    def add_mute(self, subreddit: str, username: str):
        data = {
            "api_type": "json",
            "name": username,
            "type": "muted",
        }
        return self.request(
            "POST",
            "/r/{subreddit}/api/friend".format(subreddit=subreddit),
            data=data,
        )

    def add_wiki_contributor(self, subreddit: str, username: str):
        data = {
            "api_type": "json",
            "name": username,
            "type": "wikicontributor",
        }
        return self.request(
            "POST",
            "/r/{subreddit}/api/friend".format(subreddit=subreddit),
            data=data,
        )

    def add_wiki_ban(self, subreddit: str, username: str):
        data = {
            "api_type": "json",
            "name": username,
            "type": "wikibanned",
        }
        return self.request(
            "POST",
            "/r/{subreddit}/api/friend".format(subreddit=subreddit),
            data=data,
        )

    def remove_friend(self, username: str):
        return self.request(
            "DELETE",
            "/api/v1/me/friends/{username}".format(username=username),
            data={"id": username},
        )

    def remove_moderator(self, subreddit: str, username: str):
        data = {
            "type": "moderator",
        }
        if username.startswith("t2"):
            data["id"] = username
        else:
            data["name"] = username
        return self.request(
            "POST",
            "/r/{subreddit}/api/unfriend".format(subreddit=subreddit),
            data=data,
        )

    def remove_contributor(self, subreddit: str, username: str):
        data = {
            "type": "contributor",
        }
        if username.startswith("t2"):
            data["id"] = username
        else:
            data["name"] = username
        return self.request(
            "POST",
            "/r/{subreddit}/api/unfriend".format(subreddit=subreddit),
            data=data,
        )

    def remove_ban(self, subreddit: str, username: str):
        data = {
            "type": "banned",
        }
        if username.startswith("t2"):
            data["id"] = username
        else:
            data["name"] = username
        return self.request(
            "POST",
            "/r/{subreddit}/api/unfriend".format(subreddit=subreddit),
            data=data,
        )

    def remove_mute(self, subreddit: str, username: str):
        data = {
            "type": "muted",
        }
        if username.startswith("t2"):
            data["id"] = username
        else:
            data["name"] = username
        return self.request(
            "POST",
            "/r/{subreddit}/api/unfriend".format(subreddit=subreddit),
            data=data,
        )

    def remove_wiki_contributor(self, subreddit: str, username: str):
        data = {
            "type": "wikicontributor",
        }
        if username.startswith("t2"):
            data["id"] = username
        else:
            data["name"] = username
        return self.request(
            "POST",
            "/r/{subreddit}/api/unfriend".format(subreddit=subreddit),
            data=data,
        )

    def remove_wiki_ban(self, subreddit: str, username: str):
        data = {
            "type": "wikibanned",
        }
        if username.startswith("t2"):
            data["id"] = username
        else:
            data["name"] = username
        return self.request(
            "POST",
            "/r/{subreddit}/api/unfriend".format(subreddit=subreddit),
            data=data,
        )

    # Search
    "/search"

    # Gold
    """
    /api/v1/gold/gild/fullname
    /api/v1/gold/give/username
    """
