#!/bin/bash
# Run this from: /Users/ubaidkundlik/Downloads/ai-it-support/frontend

cd /Users/ubaidkundlik/Downloads/ai-it-support/frontend

echo "Removing user/engineer/manager/chat routes..."
rm -rf src/app/chat
rm -rf src/app/tickets
rm -rf src/app/engineer
rm -rf src/app/manager
rm -rf "src/app/(auth)"

echo "Removing unused auth pages..."
rm -rf src/app/auth/register
rm -rf src/app/auth/reset-password

echo "Done. Replace src/app/auth/login/page.tsx with the new file."
echo "Restart frontend: npm run dev"