# Routes & permissions
## Users
- GET /api/internal/users
  - users
- POST /api/internal/users/apply
  - users.manage
- POST /api/internal/users/accept
  - users.manage
- POST /api/internal/users/deny
  - users.manage
- POST /api/internal/users/token
  - users.manage - may reset anyone's token
  - authorized request - may reset their own token
- POST /api/internal/users/manage
  - users.manage
- DELETE /api/internal/users/manage
  - users.manage
- POST /api/internal/users/deauth
  - users.manage
- POST /api/internal/users/auth
  - users.manage
- GET /api/bans
  - users.bans
- POST /api/bans
  - users.bans

## Public
- POST /api/public/ocr
  - public.ocr
- GET /api/public/rtfm
  - public
- GET /api/public/rtfs
  - public

## CDN
- GET /api/cdn
  - public
- POST /api/cdn
  - cdn
  - users.manage - may specify node to upload to
- GET /api/cdn/{node}/{image}
  - cdn
- DELETE /api/cdn/{node}/{image}
  - cdn - May delete an image they have uploaded
  - cdn.manage - May delete any image
- POST /api/cdn/purge
  - cdn.manage
- GET /api/cdn/list
  - cdn.manage
- GET /api/cdn/list/{user}
  - cdn.manage - May list any user
  - cdn - May list themselves
- GET /api/cdn/user
  - cdn.manage - May get any user
  - cdn - May get themselves
