# Stage 1: Build the React application
FROM node:24-alpine AS build

# Set working directory inside container
WORKDIR /app

# Copy dependency files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source code
COPY . .

# Build the production application
RUN npm run build


# Stage 2: Serve the application with Nginx
FROM nginx:alpine

# Copy built files into Nginx web directory
COPY --from=build /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
