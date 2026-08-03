module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/css");
  eleventyConfig.addPassthroughCopy("src/img");
  eleventyConfig.addPassthroughCopy("src/js");
  eleventyConfig.addPassthroughCopy({ CNAME: "CNAME" });

  eleventyConfig.addFilter("head", function (arr, n) {
    if (!Array.isArray(arr)) return [];
    return arr.slice(0, n);
  });

  eleventyConfig.addCollection("posts", function (collectionApi) {
    return collectionApi
      .getFilteredByGlob("src/posts/*.md")
      .sort((a, b) => b.date - a.date);
  });

  eleventyConfig.addCollection("categories", function (collectionApi) {
    const posts = collectionApi
      .getFilteredByGlob("src/posts/*.md")
      .sort((a, b) => b.date - a.date);
    const map = {};

    for (const name of SITE.categories) {
      map[name] = [];
    }

    for (const post of posts) {
      const cats = post.data.categories || [];
      for (const cat of cats) {
        if (!map[cat]) {
          map[cat] = [];
        }
        map[cat].push(post);
      }
    }

    return Object.keys(map)
      .sort()
      .map((name) => ({
        name,
        slug: slugify(name),
        posts: map[name],
      }));
  });

  eleventyConfig.addFilter("readableDate", function (dateObj) {
    if (!dateObj) return "";
    return new Date(dateObj).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: "UTC",
    });
  });

  eleventyConfig.addFilter("isoDate", function (dateObj) {
    if (!dateObj) return "";
    return new Date(dateObj).toISOString().slice(0, 10);
  });

  eleventyConfig.addFilter("slugify", slugify);

  eleventyConfig.addFilter("absoluteUrl", function (path) {
    const base = SITE.url.replace(/\/$/, "");
    if (!path) return base + "/";
    if (path.startsWith("http")) return path;
    return base + (path.startsWith("/") ? path : "/" + path);
  });

  eleventyConfig.addFilter("htmlDateString", function (dateObj) {
    if (!dateObj) return "";
    return new Date(dateObj).toISOString();
  });

  // Click-to-play YouTube embed (static thumbnail until clicked)
  eleventyConfig.addShortcode("youtube", function (id) {
    if (!id) return "";
    const videoId = String(id).trim();
    const thumb = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
    return `<div class="youtube-lite" data-id="${videoId}">
  <button type="button" class="youtube-lite__btn" aria-label="Play YouTube video">
    <img class="youtube-lite__thumb" src="${thumb}" alt="" width="480" height="360" loading="lazy">
    <span class="youtube-lite__play" aria-hidden="true"></span>
  </button>
</div>`;
  });

  return {
    dir: {
      input: "src",
      includes: "_includes",
      data: "_data",
      output: "_site",
    },
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
    templateFormats: ["njk", "md", "html"],
  };
};

function slugify(str) {
  return String(str)
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

// ============================================================
// USER-DEFINED SETTINGS (edit these)
// ============================================================
const SITE = {
  title: "Uncle Mike's Garage",
  tagline: "Fixing, building, and tinkering in the workshop",
  author: "Uncle Mike",
  url: "https://unclemikesgarage.com",
  youtubeChannel: "https://www.youtube.com/@UncleMikesGarage",
  githubRepo: "https://github.com/mike-cline-53/unclemikesgarage",
  categories: [
    "Woodworking",
    "CNC",
    "3D Printing",
    "Automotive",
    "Restoration",
    "Shop Talk",
  ],
  postsPerPage: 10,
};
