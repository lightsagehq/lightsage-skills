# Myths to push back on

Read when the user asks for one of these, or a checklist they found recommends it. Answer in one line, then point to what does work.

| Claim | Reality | Do instead |
|---|---|---|
| "Add llms.txt so ChatGPT / Perplexity / Google rank or cite us." | No major answer engine has said it uses llms.txt for ranking or citation; Google has said Search does not use it. Coding agents and people pasting docs into an agent do use it. | Ship it for docs as a cheap index for coding agents; fix access and content for answer engines. |
| "Meta keywords help AI search." | Ignored by Google since 2009 and by every AI engine. | Clear titles, descriptions and on-page facts. |
| "Add AI meta tags / ai.txt / a hidden 'for AI' block." | No provider reads them. Hidden text risks looking like cloaking. | Clean server-rendered HTML; markdown on `Accept: text/markdown`. |
| "Block GPTBot and we disappear from ChatGPT." | GPTBot is training only. ChatGPT search uses OAI-SearchBot; page opens use ChatGPT-User. | Decide training, search and user access separately. |
| "Allow GPTBot and ChatGPT will cite us." | Training is not citation. Citations come from search and live fetches. | Allow OAI-SearchBot and ChatGPT-User; earn citations with content. |
| "Blocking Google-Extended removes us from AI Overviews." | AI Overviews and AI Mode use Googlebot's crawl; Google-Extended controls Gemini training and grounding only. | Use `nosnippet` / `data-nosnippet` if you must limit snippets. |
| "robots.txt keeps AI scrapers out." | Only compliant crawlers obey it; user-triggered fetchers may not. | Enforce at the CDN with verified-bot rules if you need a block. |
| "Our robots.txt allows everything, so bots can read us." | CDN/WAF rules, bot fight modes and challenges block by user agent regardless of robots.txt. | Fetch as each agent (this skill's script) and check the CDN dashboard. |
| "Serve markdown to bots to save them tokens." | Choosing markdown by user agent is cloaking, and returning markdown to OpenAI's crawlers broke ChatGPT citations in a real case. | Markdown only on request (`Accept` or `.md` URL), with `Vary: Accept`. |
| "JSON-LD makes LLMs understand us." | Models read page text; structured data mainly feeds search indexes and rich results. | Keep schema accurate for search; put facts in visible text. |
| "An agent-readiness score of 100 means agents can use us." | Scores count checklist items; they do not show whether a real agent fetched and used the page. | Evidence from real fetches, then real agent tasks (`test-api-on-agents`). |
| "We need to submit our sitemap to ChatGPT / Claude." | There is no submission. ChatGPT search draws partly on third-party indexes such as Bing. | Keep sitemaps in robots.txt; register with Bing Webmaster Tools / IndexNow and Google Search Console. |
