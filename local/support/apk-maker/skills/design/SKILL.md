---
name: design
description: Make the app look finished and polished with Material 3 - the phone's own colours (dynamic colour), dark mode, clear typography and spacing, empty states, adaptive layouts for landscape and tablets, and accessibility. Use for every app before calling it done, and whenever the user asks for nicer looks, colours, a theme or a cleaner layout.
---

# Looking finished

Working code: `example/Theme.kt` (`AppTheme` with dynamic colour and dark mode, `EmptyState`,
`SectionHeader`, and a screen that adapts to wide windows).

## Theme

- Wrap the app in `AppTheme { ... }` (example) instead of a bare `MaterialTheme`: on Android 12+ it takes
  the colours from the user's wallpaper, otherwise it uses the app's own palette, light or dark.
- Pick one seed colour that fits the app (green for money, blue for calm, orange for energy) and use it
  for the fallback scheme and the launcher icon background.
- Colours only from `MaterialTheme.colorScheme` (`primary`, `surfaceContainer`…), never hard-coded hex
  in screens: then dark mode and dynamic colour just work.

## Layout

- Spacing on an 8 dp grid: 16 dp screen padding, 8 or 12 dp between items, 24 dp between sections.
- Typography from `MaterialTheme.typography`: `headlineSmall` for a screen's main number or title,
  `titleMedium` for card titles, `bodyMedium` for text, `labelMedium` for small labels.
- Lists: `LazyColumn` with `key`s, `ListItem` rows; cards (`ElevatedCard`, `OutlinedCard`) for grouped
  content.
- Every list or screen that can be empty shows an `EmptyState`: an icon, one line on what goes here, and
  the button that adds the first item.
- Wide windows (landscape, tablets, foldables): `BoxWithConstraints`, and above 600 dp show two panes
  or a centred column at most 640 dp wide (example).

## Polish checklist

- A real app name in `strings.xml`, a launcher icon that matches the app (see AGENTS.md).
- Touch targets at least 48 dp; every icon button has a `contentDescription`.
- Text contrast: on-colours on their colours (`onPrimary` on `primary`), never grey on grey.
- Feedback for every action: a Snackbar or a visible change.
- Numbers formatted for people: `NumberFormat.getCurrencyInstance()`, dates with `DateTimeFormatter`.
