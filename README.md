# PyGPT

An unofficial wrapper for ChatGPT using httpx.

Installation:

```shell
$ git clone https://github.com/stefan2200/PyGPT
$ cd PyGPT
$ pip install -r requirements.txt
$ python3 pygpt.py -h
Usage: pygpt.py [options]

Options:
  -h, --help   show this help message and exit
  -u EMAIL     The OpenAI account mail address
  -p PASSWORD  The OpenAI account password
  -q QUERY     Run this query and exit
  -v           Show verbose information
  -m           Enable moderation requests
```

Basic usage (CLI):

```
$ python3 pygpt.py -u "user@example.com" -p "YourPassword"
Starting in CLI mode
Send 'reset' to discard the current conversation, 'exit' to quit
INFO:root:Starting new session
INFO:root:Authenticating as user@example.com
INFO:root:Authentication successful
Query> What is 6+4?
6+4 is equal to 10. This is a basic mathematical equation that represents the addition of two numbers.


Query> reset
Resetting conversation
Query>
```

Using the API:

```python
from pygpt import ChatGPT

email = "user@example.com"
password = "YourPassword"
queries = [
    "What are the 5 most healthy foods available?",
    "And how about fruits?"
]

bot = ChatGPT(
    email,
    password
)
bot.auth()
for q in queries:
    result = bot.do_query(q, return_text=False)
    # Return a dict object
    print(result)
    # _example = {'id': 'UUID', 'role': 'assistant', 'user': None, 'create_time': None, 'update_time': None, 'content': {'content_type': 'text', 'parts': ['The square root of 3 is approximately 1.7320508075688772935274463415059.']}, 'end_turn': None, 'weight': 1.0, 'metadata': {}, 'recipient': 'all'}
# reset the conversation
bot.last_parent = None
```