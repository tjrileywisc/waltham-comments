
# Waltham comments page

This page displays a video with recognized speaker captions and a list of other videos that can be shown.

## Running it

Dev mode:
Run `uvicorn main:app --reload`

(a production mode isn't ready yet)

Environment to set

`DATA_DIR` the path to the root of the processing repo. Should be changed later...

## The frontend code

The frontend is a React app build with npm modules. `cd` into that directory and run `npm run build` to put the relevant files in the expected place for the backend
to allow the server to run.
