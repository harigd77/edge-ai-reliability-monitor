const express = require('express');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const client = require('prom-client');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const winston = require('winston');

// Configure logging
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.Console(),
    new winston.transports.File({ filename: 'auth-service.log' })
  ]
});

// Initialize Express app
const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100 // limit each IP to 100 requests per windowMs
});
app.use(limiter);

// Prometheus Metrics
const register = new client.Registry();
client.collectDefaultMetrics({ register });

// Custom metrics
const httpRequestDuration = new client.Histogram({
  name: 'auth_http_request_duration_seconds',
  help: 'Duration of HTTP requests in seconds',
  labelNames: ['method', 'route', 'status_code'],
  registers: [register]
});

const authAttempts = new client.Counter({
  name: 'auth_attempts_total',
  help: 'Total authentication attempts',
  labelNames: ['result'],
  registers: [register]
});

const activeTokens = new client.Gauge({
  name: 'auth_active_tokens',
  help: 'Number of active authentication tokens',
  registers: [register]
});

const cpuUsage = new client.Gauge({
  name: 'auth_cpu_usage_percent',
  help: 'Auth service CPU usage percentage',
  registers: [register]
});

const memoryUsage = new client.Gauge({
  name: 'auth_memory_usage_mb',
  help: 'Auth service memory usage in MB',
  registers: [register]
});

// Simulated user database
const users = [
  {
    id: 1,
    username: 'admin',
    password: '$2a$10$rOzJqQjQjQjQjQjQjQjQjOzJqQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQ', // 'password'
    role: 'admin',
    permissions: ['read', 'write', 'admin']
  },
  {
    id: 2,
    username: 'user',
    password: '$2a$10$rOzJqQjQjQjQjQjQjQjQjOzJqQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQ', // 'password'
    role: 'user',
    permissions: ['read']
  },
  {
    id: 3,
    username: 'operator',
    password: '$2a$10$rOzJqQjQjQjQjQjQjQjQjOzJqQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQjQ', // 'password'
    role: 'operator',
    permissions: ['read', 'write']
  }
];

// JWT Secret
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production';

// Active tokens store (in production, use Redis)
let activeTokensStore = new Set();

// Middleware to track metrics
app.use((req, res, next) => {
  const start = Date.now();
  
  res.on('finish', () => {
    const duration = (Date.now() - start) / 1000;
    httpRequestDuration
      .labels(req.method, req.route?.path || req.path, res.statusCode)
      .observe(duration);
    
    // Simulate resource usage
    cpuUsage.set(Math.random() * 50 + 10);
    memoryUsage.set(Math.random() * 100 + 50);
  });
  
  next();
});

// Routes
app.get('/', (req, res) => {
  res.json({ 
    message: 'Edge AI Reliability Monitor - Authentication Service',
    status: 'running',
    version: '1.0.0'
  });
});

app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy', 
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.post('/auth/login', async (req, res) => {
  try {
    const { username, password } = req.body;
    
    if (!username || !password) {
      authAttempts.labels('failed').inc();
      return res.status(400).json({ error: 'Username and password required' });
    }
    
    // Find user
    const user = users.find(u => u.username === username);
    if (!user) {
      authAttempts.labels('failed').inc();
      logger.warn(`Login attempt for non-existent user: ${username}`);
      return res.status(401).json({ error: 'Invalid credentials' });
    }
    
    // Verify password (using plain comparison for demo, bcrypt in production)
    const validPassword = await bcrypt.compare(password, user.password);
    if (!validPassword) {
      authAttempts.labels('failed').inc();
      logger.warn(`Failed login attempt for user: ${username}`);
      return res.status(401).json({ error: 'Invalid credentials' });
    }
    
    // Generate JWT token
    const token = jwt.sign(
      { 
        userId: user.id, 
        username: user.username, 
        role: user.role,
        permissions: user.permissions
      },
      JWT_SECRET,
      { expiresIn: '1h' }
    );
    
    activeTokensStore.add(token);
    activeTokens.set(activeTokensStore.size);
    
    authAttempts.labels('success').inc();
    logger.info(`User logged in: ${username}`);
    
    res.json({
      message: 'Login successful',
      token,
      user: {
        id: user.id,
        username: user.username,
        role: user.role,
        permissions: user.permissions
      }
    });
    
  } catch (error) {
    logger.error('Login error:', error);
    authAttempts.labels('failed').inc();
    res.status(500).json({ error: 'Internal server error' });
  }
});

app.post('/auth/logout', (req, res) => {
  try {
    const token = req.headers.authorization?.replace('Bearer ', '');
    
    if (token) {
      activeTokensStore.delete(token);
      activeTokens.set(activeTokensStore.size);
    }
    
    logger.info('User logged out');
    res.json({ message: 'Logout successful' });
    
  } catch (error) {
    logger.error('Logout error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

app.post('/auth/verify', (req, res) => {
  try {
    const token = req.headers.authorization?.replace('Bearer ', '');
    
    if (!token) {
      return res.status(401).json({ error: 'Token required' });
    }
    
    const decoded = jwt.verify(token, JWT_SECRET);
    
    if (!activeTokensStore.has(token)) {
      return res.status(401).json({ error: 'Token has been revoked' });
    }
    
    res.json({
      valid: true,
      user: decoded
    });
    
  } catch (error) {
    if (error.name === 'TokenExpiredError') {
      // Remove expired token from active store
      const token = req.headers.authorization?.replace('Bearer ', '');
      if (token) {
        activeTokensStore.delete(token);
        activeTokens.set(activeTokensStore.size);
      }
      return res.status(401).json({ error: 'Token expired' });
    }
    
    logger.error('Token verification error:', error);
    res.status(401).json({ error: 'Invalid token' });
  }
});

app.get('/auth/stats', (req, res) => {
  try {
    const stats = {
      active_tokens: activeTokensStore.size,
      total_users: users.length,
      auth_attempts: authAttempts.get(),
      uptime_seconds: process.uptime(),
      memory_usage_mb: process.memoryUsage().heapUsed / 1024 / 1024,
      cpu_usage_percent: Math.random() * 50 + 10
    };
    
    res.json(stats);
    
  } catch (error) {
    logger.error('Stats error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Error handling middleware
app.use((err, req, res, next) => {
  logger.error('Unhandled error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

// Start server
app.listen(PORT, () => {
  logger.info(`Auth service running on port ${PORT}`);
  console.log(`Auth service running on port ${PORT}`);
});

module.exports = app;
