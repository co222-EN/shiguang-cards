# Shiguang Cards PWA

拾光卡片是一个手机优先的拍照记录 PWA。手机像 App 一样打开，拍照后自动裁剪、识别物品或食物、估算卡路里，并保存成一张生活记录卡片。

## Features

- 手机拍照或上传图片
- 自动生成 4:5 Ins 风记录卡片图和缩略图
- 食物/饮品会使用更稳定的柔和相框效果，避免不准的自动抠图破坏画面
- OpenAI 视觉识别，返回结构化标签、标题、文案和食物热量估算
- 本地开发默认保存到 `data/`
- 部署时可切换到 Supabase Postgres + Storage
- PWA 支持添加到手机桌面、离线打开、离线草稿和联网同步
- API Key 未配置时仍可保存照片，AI 状态显示为待配置

## Quick Start

```powershell
cd E:\isfp-moment-journal
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8502
```

Open `http://localhost:8502` on the computer. On a phone in the same Wi-Fi network, open `http://<computer-ip>:8502`.

For true phone-independent use, deploy this project to Render, Railway, or Fly.io and configure Supabase plus OpenAI environment variables.

## Environment

`APP_PASSCODE` is optional for local development. Set it in production so only you can open the API.

```env
APP_PASSCODE=change-me
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini
STORAGE_BACKEND=local
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=moment-photos
```

## Supabase Setup

1. Create a Supabase project.
2. Run `supabase_schema.sql` in the SQL editor.
3. Create a public Storage bucket named `moment-photos`.
4. Set these environment variables in your hosting service:
   - `STORAGE_BACKEND=supabase`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_STORAGE_BUCKET=moment-photos`
   - `OPENAI_API_KEY`
   - `APP_PASSCODE`

The service role key must stay on the server. Do not put it in frontend code.

## API

- `POST /api/session`
- `GET /api/session`
- `POST /api/records`
- `GET /api/records`
- `PATCH /api/records/{id}`
- `DELETE /api/records/{id}`
- `POST /api/analyze`
- `GET /api/me/export`

## Notes

Calorie output is an estimate for personal journaling only. It is not medical or nutrition advice.
