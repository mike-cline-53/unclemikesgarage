---
layout: base.njk
title: About
permalink: /about/
---
<article class="panel prose">
  <h1>About Uncle Mike's Garage</h1>
  <p>
    I'm Mike — and this is the digital workshop door for
    <strong>Uncle Mike's Garage</strong>. Out in the real garage you'll find me
    fixing and refurbishing old things, cutting wood, running the CNC,
    printing plastic parts, wrenching on cars, and generally making a pleasant
    mess.
  </p>
  <p>
    The YouTube channel is where the videos live. This site is where I write
    about the projects: notes, photos, mistakes, and the bits that didn't make
    the cut.
  </p>
  <p>
    Categories you'll see around here:
  </p>
  <ul>
    {% for cat in site.categories %}
    <li><a href="/category/{{ cat | slugify }}/">{{ cat }}</a></li>
    {% endfor %}
  </ul>
  <p>
    Prefer a feed reader?
    <a href="/feed.xml">Subscribe via RSS</a>.
    Prefer moving pictures?
    <a href="{{ site.youtubeChannel }}" rel="noopener noreferrer" target="_blank">Subscribe on YouTube</a>.
  </p>
  <p>
    <img class="construction" src="/img/under-construction.gif" alt="" width="38" height="38">
    Site forever under construction, same as the shop.
    <img class="construction" src="/img/under-construction.gif" alt="" width="38" height="38">
  </p>
</article>
