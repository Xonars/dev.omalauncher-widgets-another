# TAGLINE

captures screenshots of websites at specified viewport sizes

# TLDR

**Screenshot a website**

```pageres [https://example.com]```

**Specify viewport size**

```pageres [https://example.com] [1024x768]```

**Multiple sizes**

```pageres [https://example.com] [1024x768] [1920x1080]```

**Crop to viewport** (default is full page)

```pageres [https://example.com] [1024x768] --crop```

**Set output filename**

```pageres [https://example.com] --filename=[screenshot]```

**Delay before capture**

```pageres [https://example.com] --delay=[3]```

**Set output directory**

```pageres [https://example.com] -d [./screenshots]```

**Capture a specific element**

```pageres [https://example.com] --selector=[.header]```

**Hide an element before capture**

```pageres [https://example.com] --hide=[.cookie-banner]```

# SYNOPSIS

**pageres** [_options_] _url_ [_sizes_...]

# PARAMETERS

**-d**, **--dest** _DIR_
> Output directory.

**--filename** _TEMPLATE_
> Filename template.

**--delay** _SECONDS_
> Delay before screenshot.

**-c**, **--crop**
> Crop image to the specified viewport height (default captures the full scrolling page).

**--overwrite**
> Overwrite existing files.

**--format** _FORMAT_
> Image format: _png_ (default) or _jpg_.

**--scale** _FACTOR_
> Pixel-density scale multiplier.

**--selector** _SELECTOR_
> Capture only the DOM element matching the CSS selector.

**--hide** _SELECTOR_
> Hide elements matching the selector before capture (repeatable).

**--clickElement** _SELECTOR_
> Click the matched element before capture.

**--css** _CSS_
> Inject custom CSS before capture.

**--cookie** _COOKIE_
> Cookie string (repeatable).

**--header** _HEADER_
> HTTP header (repeatable).

**--username** _USER_
> HTTP basic auth username.

**--password** _PASS_
> HTTP basic auth password.

**--user-agent** _UA_
> User agent string.

**--transparent**
> Use a transparent background instead of white.

**--darkMode**
> Emulate the user's dark color scheme preference.

**--timeout** _SECONDS_
> Request timeout in seconds.

**-v**, **--verbose**
> Print detailed error output.

# DESCRIPTION

**pageres** captures screenshots of websites at specified viewport sizes. It's useful for responsive design testing.

Multiple viewport sizes can be specified in a single command. Each size produces a separate image.

Full-page screenshots capture content below the fold. Cropping limits output to visible viewport.

Delays allow JavaScript and animations to complete. Custom CSS can hide or modify elements.

Output supports PNG and JPEG formats. Filenames can include URL and size variables.

# CAVEATS

Requires headless Chrome/Chromium. JavaScript-heavy sites may need delays. Some sites block automated screenshots.

# HISTORY

**pageres** was created by **Sindre Sorhus** for responsive design testing. It provides a command-line interface for website screenshot automation.

# SEE ALSO

[chromium](/man/chromium)(1), [puppeteer](/man/puppeteer)(1), [shot-scraper](/man/shot-scraper)(1)
