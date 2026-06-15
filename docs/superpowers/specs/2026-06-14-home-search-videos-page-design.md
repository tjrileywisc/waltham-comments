# Home Page Search + Videos Page Design

**Date:** 2026-06-14  
**Branch:** prominent-search

## Goal

Move the video listing to its own `/videos` page and make the home page a centered search experience.

## Routes

| Route | Component | Description |
|---|---|---|
| `/` | `Search.jsx` | Search box centered vertically; results flow below |
| `/videos` | `Videos.jsx` | Two-pane: VideoPlayer + TranscriptDisplay (left), VideoList (right) |
| `/search` | removed | Old search route eliminated; home is now search |

## Component Changes

### `App.jsx` → `Videos.jsx`
Rename file and component. No logic changes. The two-pane layout (VideoPlayer + TranscriptDisplay on left, VideoList on right) stays identical.

### `index.jsx`
- Route `/` → `<Search />`
- Route `/videos` → `<Videos />`
- Remove route `/search`

### `Navbar.jsx`
- Remove "Search" link (home is now search)
- Add "Videos" link pointing to `/videos`

### `Search.jsx`
- Update result links from `/?video=...&t=...` to `/videos?video=...&t=...`

## CSS Changes

### `styles.css`
Add a rule so `search-container` is vertically centered on the home page:

```css
.search-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 60px); /* subtract navbar height */
  flex-direction: column;
}
```

Rename the root `<div className="search-container">` in `Search.jsx` to `<div className="search-page">`. Results appear below the search form; the page scrolls naturally as content grows.

## Out of Scope

- No changes to VideoPlayer, TranscriptDisplay, VideoList logic
- No changes to backend API
- No styling changes beyond centering the search box
