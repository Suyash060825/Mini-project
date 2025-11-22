# Use Debian-slim for best compatibility
FROM node:20-slim

WORKDIR /app

# 1. Copy ONLY package.json
# We DO NOT copy package-lock.json. This forces NPM to generate a new one 
# specifically for Linux, ensuring the correct Rollup binaries are downloaded.
COPY frontend/package.json .

# 2. Install dependencies cleanly
# We do NOT use --no-optional here. We need the optional linux binaries.
RUN npm install

# 3. Copy the rest of the app
COPY frontend/. .

# Expose the port
EXPOSE 5173

# Start the server binding to all interfaces
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]