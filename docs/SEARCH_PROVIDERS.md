# Search providers

Deeper Dive's initial automated public-web search backend is SearXNG. Configure the base URL of a SearXNG instance whose operator permits API use and has JSON output enabled. Deeper Dive sends bounded `/search?format=json` requests and does not require credentials by default; deployments may place their own authenticated proxy in front of SearXNG if needed.

Normal CI never calls a live search service. Search behavior is covered with deterministic fake providers and mocked SearXNG responses. Operators are responsible for the terms, rate limits, and acceptable-use policy of the SearXNG instance and of the upstream engines configured by that instance.
