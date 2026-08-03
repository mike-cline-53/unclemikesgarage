# Uncle Mike's Garage

Retro 90s workshop blog for [unclemikesgarage.com](https://unclemikesgarage.com), built with [Eleventy](https://www.11ty.dev/).

## Local development

Requires Node 18+.

```bash
npm install
npm start
```

Open http://localhost:8080

Build once without the server:

```bash
npm run build
```

## Writing a post

Add a Markdown file under `src/posts/`:

```markdown
---
title: Your Post Title
date: 2026-08-15
categories: [Woodworking, CNC]
video: YOUTUBE_VIDEO_ID
summary: One-line teaser for the homepage.
---

Your write-up here. Optional video embeds via the front-matter `video` field
(click-to-play thumbnail — no YouTube JS until the visitor clicks).
```

Categories are defined in `src/_data/site.js` and `eleventy.config.js` (same list in both — keep them in sync when you add one).

## Tunable settings

All user-defined knobs live at the **bottom** of `eleventy.config.js` and in `src/_data/site.js`:

- Site title, tagline, author, URL
- YouTube channel and GitHub repo links
- Category list
- Posts per page on the homepage

## Deploy

Push to `main`. GitHub Actions builds with Eleventy and publishes to GitHub Pages.

Repo: `mike-cline-53/unclemikesgarage`

### Enable GitHub Pages (one-time)

1. Open the repo on GitHub → **Settings** → **Pages**
2. Under **Build and deployment** → **Source**, choose **GitHub Actions**
3. Confirm the custom domain is `unclemikesgarage.com` (the `CNAME` file in the repo sets this)

### Squarespace DNS (one-time)

Keep the domain registered at Squarespace; only change where it points.

1. Log into [Squarespace](https://account.squarespace.com/) → **Domains** → **unclemikesgarage.com**
2. Open **DNS Settings** (sometimes labeled **Advanced settings**)
3. Remove Squarespace's default website records that conflict (their default A / CNAME / ALIAS pointing at Squarespace hosting)
4. Add these records for the **apex** (root domain):

| Type | Host | Data |
|------|------|------|
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |

5. Add this for **www**:

| Type | Host | Data |
|------|------|------|
| CNAME | `www` | `mike-cline-53.github.io` |

6. Save. Propagation can take from a few minutes up to 48 hours.
7. Back in GitHub → **Settings** → **Pages**, wait until the custom domain shows a successful TLS certificate (HTTPS). GitHub issues this free once DNS verifies.

Your existing Squarespace *site* can stay up until you flip these records — then traffic goes to GitHub Pages instead.

## License

MIT
