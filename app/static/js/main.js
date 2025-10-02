// PostgreSQL Replication Manager - Main JavaScript

class ReplicationManager {
    constructor() {
        this.currentPage = 'dashboard';
        this.refreshInterval = null;
        this.init();
    }

    init() {
        this.setupNavigation();
        this.setupAutoRefresh();
        this.loadInitialData();
    }

    setupNavigation() {
        // Handle navigation clicks
        document.addEventListener('click', (e) => {
            if (e.target.matches('[data-page]')) {
                e.preventDefault();
                const page = e.target.getAttribute('data-page');
                this.navigateTo(page);
            }
        });

        // Set active nav item based on current page
        this.updateActiveNav();
    }

    navigateTo(page) {
        this.currentPage = page;
        this.updateActiveNav();
        this.loadPageContent(page);
        
        // Update URL without page reload
        const url = new URL(window.location);
        url.searchParams.set('page', page);
        window.history.pushState({page}, '', url);
    }

    updateActiveNav() {
        // Remove active class from all nav items
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.classList.remove('active');
        });

        // Add active class to current page nav item
        const activeTab = document.querySelector(`[data-page="${this.currentPage}"]`)?.closest('.nav-tab');
        if (activeTab) {
            activeTab.classList.add('active');
        }
    }

    async loadPageContent(page) {
        const contentArea = document.getElementById('main-content');
        if (!contentArea) return;

        // Show loading state
        contentArea.innerHTML = '<div class="text-center"><div class="spinner"></div> Loading...</div>';

        try {
            switch (page) {
                case 'dashboard':
                    await this.loadDashboard();
                    break;
                case 'topology':
                    await this.loadTopology();
                    break;
                case 'databases':
                    await this.loadDatabases();
                    break;
                case 'replication':
                    await this.loadReplication();
                    break;
                case 'migrations':
                    await this.loadMigrations();
                    break;
                default:
                    contentArea.innerHTML = '<div class="card"><div class="card-body">Page not found</div></div>';
            }
        } catch (error) {
            console.error('Error loading page content:', error);
            contentArea.innerHTML = `
                <div class="card">
                    <div class="card-body">
                        <div class="status error">
                            <span>⚠️</span>
                            Error loading content: ${error.message}
                        </div>
                    </div>
                </div>
            `;
        }
    }

    async loadDashboard() {
        const [systemStatus, dbStatus, replicationStatus] = await Promise.all([
            this.fetchSystemStatus(),
            this.fetchDatabaseStatus(),
            this.fetchReplicationStatus()
        ]);

        const content = `
            <h1 class="page-title">Dashboard</h1>
            
            <div class="row">
                <div class="col-4">
                    <div class="card">
                        <div class="card-header">System Status</div>
                        <div class="card-body">
                            <div class="status ${systemStatus.status}">
                                <span>${systemStatus.icon}</span>
                                ${systemStatus.message}
                            </div>
                            <div class="mt-2">
                                <small>Last updated: ${new Date().toLocaleTimeString()}</small>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-4">
                    <div class="card">
                        <div class="card-header">Databases</div>
                        <div class="card-body">
                            <div class="status ${dbStatus.status}">
                                <span>${dbStatus.icon}</span>
                                ${dbStatus.healthy}/${dbStatus.total} healthy
                            </div>
                            <div class="mt-2">
                                <small>Response time: ${dbStatus.avgResponseTime}ms</small>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-4">
                    <div class="card">
                        <div class="card-header">Replication Streams</div>
                        <div class="card-body">
                            <div class="status ${replicationStatus.status}">
                                <span>${replicationStatus.icon}</span>
                                ${replicationStatus.active}/${replicationStatus.total} active
                            </div>
                            <div class="mt-2">
                                <small>Avg lag: ${replicationStatus.avgLag}ms</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">Recent Activity</div>
                <div class="card-body">
                    <div id="recent-activity">Loading recent activity...</div>
                </div>
            </div>
        `;

        document.getElementById('main-content').innerHTML = content;
        
        // Load recent activity
        this.loadRecentActivity();
    }

    async loadTopology() {
        const content = `
            <h1 class="page-title">Replication Topology</h1>
            
            <div class="card">
                <div class="card-header">
                    <div class="d-flex justify-content-between align-items-center">
                        <span>Topology Visualization</span>
                        <button class="btn btn-primary btn-sm" onclick="replicationManager.refreshTopology()">
                            <span id="refresh-icon">🔄</span> Refresh
                        </button>
                    </div>
                </div>
                <div class="card-body">
                    <div id="topology-container" style="height: 500px; border: 1px solid #dee2e6; border-radius: 4px;">
                        <div class="text-center" style="padding: 2rem;">
                            <div class="spinner"></div>
                            <div class="mt-2">Loading topology...</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="row">
                <div class="col-6">
                    <div class="card">
                        <div class="card-header">Databases</div>
                        <div class="card-body">
                            <div id="databases-list">Loading...</div>
                        </div>
                    </div>
                </div>
                
                <div class="col-6">
                    <div class="card">
                        <div class="card-header">Replication Streams</div>
                        <div class="card-body">
                            <div id="streams-list">Loading...</div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.getElementById('main-content').innerHTML = content;
        
        // Load topology data and render visualization
        await this.loadTopologyVisualization();
    }

    async loadDatabases() {
        const content = `
            <h1 class="page-title">Database Management</h1>
            
            <div class="card">
                <div class="card-header">
                    <div class="d-flex justify-content-between align-items-center">
                        <span>Database Configurations</span>
                        <div>
                            <button class="btn btn-outline-primary btn-sm" onclick="replicationManager.testAllConnections()">
                                Test All
                            </button>
                            <button class="btn btn-primary btn-sm" onclick="replicationManager.showAddDatabaseModal()">
                                Add Database
                            </button>
                        </div>
                    </div>
                </div>
                <div class="card-body">
                    <div id="databases-table">Loading databases...</div>
                </div>
            </div>

            <!-- Add Database Modal -->
            <div id="add-database-modal" class="modal" style="display: none;">
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>Add Database Configuration</h3>
                        <button class="btn-close" onclick="replicationManager.hideAddDatabaseModal()">&times;</button>
                    </div>
                    <div class="modal-body">
                        <form id="add-database-form">
                            <div class="row">
                                <div class="col-6">
                                    <div class="form-group">
                                        <label class="form-label">Name</label>
                                        <input type="text" class="form-control" name="name" required>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="form-group">
                                        <label class="form-label">Role</label>
                                        <select class="form-control" name="role" required>
                                            <option value="">Select role...</option>
                                            <option value="primary">Primary</option>
                                            <option value="replica">Replica</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-6">
                                    <div class="form-group">
                                        <label class="form-label">Host</label>
                                        <input type="text" class="form-control" name="host" required>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="form-group">
                                        <label class="form-label">Port</label>
                                        <input type="number" class="form-control" name="port" value="5432" required>
                                    </div>
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Database Name</label>
                                <input type="text" class="form-control" name="database" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Credentials ARN</label>
                                <input type="text" class="form-control" name="credentials_arn" required>
                            </div>
                            <div class="row">
                                <div class="col-6">
                                    <div class="form-group">
                                        <label class="form-label">Environment</label>
                                        <select class="form-control" name="environment" required>
                                            <option value="">Select environment...</option>
                                            <option value="development">Development</option>
                                            <option value="staging">Staging</option>
                                            <option value="production">Production</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="form-group">
                                        <label class="form-label">Cloud Provider</label>
                                        <select class="form-control" name="cloud_provider">
                                            <option value="aws">AWS</option>
                                            <option value="gcp">Google Cloud</option>
                                            <option value="azure">Azure</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="form-label">VPC ID</label>
                                <input type="text" class="form-control" name="vpc_id">
                            </div>
                            <div class="form-group">
                                <label>
                                    <input type="checkbox" name="use_iam_auth"> Use IAM Authentication
                                </label>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="replicationManager.hideAddDatabaseModal()">Cancel</button>
                        <button class="btn btn-primary" onclick="replicationManager.submitAddDatabase()">Add Database</button>
                    </div>
                </div>
            </div>
        `;

        document.getElementById('main-content').innerHTML = content;
        
        // Load databases table
        await this.loadDatabaseConfigsTable();
    }

    async loadReplication() {
        const content = `
            <h1 class="page-title">Replication Management</h1>
            
            <div class="card">
                <div class="card-header">
                    <div class="d-flex justify-content-between align-items-center">
                        <span>Replication Streams</span>
                        <div>
                            <button class="btn btn-outline-primary btn-sm" onclick="replicationManager.discoverReplication()">
                                Discover
                            </button>
                            <button class="btn btn-primary btn-sm" onclick="replicationManager.showCreateStreamModal()">
                                Create Stream
                            </button>
                        </div>
                    </div>
                </div>
                <div class="card-body">
                    <div id="replication-streams">Loading replication streams...</div>
                </div>
            </div>
        `;

        document.getElementById('main-content').innerHTML = content;
        
        // Load replication streams
        await this.loadReplicationStreams();
    }

    async loadMigrations() {
        const content = `
            <h1 class="page-title">Schema Migrations</h1>
            
            <div class="card">
                <div class="card-header">
                    <div class="d-flex justify-content-between align-items-center">
                        <span>Migration Execution</span>
                        <div>
                            <button class="btn btn-outline-primary btn-sm" onclick="replicationManager.loadSampleMigration()">
                                Load Sample
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="replicationManager.clearMigrationEditor()">
                                Clear
                            </button>
                        </div>
                    </div>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-6">
                            <h5>SQL Editor</h5>
                            <textarea id="migration-sql" class="form-control" rows="15" placeholder="-- Enter your SQL migration script here
-- Example:
-- CREATE TABLE users (
--     id SERIAL PRIMARY KEY,
--     username VARCHAR(50) UNIQUE NOT NULL,
--     email VARCHAR(100) UNIQUE NOT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );"></textarea>
                            
                            <div class="mt-2">
                                <div class="form-group">
                                    <label>
                                        <input type="checkbox" id="dry-run-checkbox" checked> Dry Run (validate only)
                                    </label>
                                </div>
                                <div class="form-group">
                                    <label>
                                        <input type="checkbox" id="rollback-checkbox" checked> Rollback on error
                                    </label>
                                </div>
                            </div>
                            
                            <div class="mt-2">
                                <button class="btn btn-success" onclick="replicationManager.executeMigration()" id="execute-btn">
                                    <span id="execute-icon">▶️</span> Execute Migration
                                </button>
                                <button class="btn btn-secondary" onclick="replicationManager.validateMigration()">
                                    ✓ Validate Only
                                </button>
                            </div>
                        </div>
                        <div class="col-6">
                            <h5>Execution Results</h5>
                            <div id="migration-results" class="border p-3" style="height: 400px; overflow-y: auto; background: #f8f9fa; font-family: monospace; font-size: 0.875rem;">
                                <div class="text-muted">Migration results will appear here...</div>
                            </div>
                            
                            <div class="mt-2">
                                <div id="migration-progress" class="progress" style="display: none;">
                                    <div class="progress-bar" role="progressbar" style="width: 0%"></div>
                                </div>
                                <div id="migration-status" class="mt-2"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">Migration History</div>
                <div class="card-body">
                    <div id="migration-history">Loading migration history...</div>
                </div>
            </div>
        `;

        document.getElementById('main-content').innerHTML = content;
        
        // Load migration history
        await this.loadMigrationHistory();
        
        // Setup WebSocket for real-time progress if available
        this.setupMigrationWebSocket();
    }

    // API Methods
    async fetchSystemStatus() {
        try {
            const response = await fetch('/health');
            const data = await response.json();
            return {
                status: data.status === 'healthy' ? 'healthy' : 'error',
                icon: data.status === 'healthy' ? '✅' : '❌',
                message: data.status === 'healthy' ? 'All systems operational' : 'System issues detected'
            };
        } catch (error) {
            return {
                status: 'error',
                icon: '❌',
                message: 'Unable to connect to system'
            };
        }
    }

    async fetchDatabaseStatus() {
        try {
            const response = await fetch('/api/databases/test');
            const data = await response.json();
            return {
                status: data.overall_status === 'healthy' ? 'healthy' : 'warning',
                icon: data.overall_status === 'healthy' ? '✅' : '⚠️',
                healthy: data.healthy_databases,
                total: data.total_databases,
                avgResponseTime: Math.round(data.databases.reduce((sum, db) => sum + db.response_time_ms, 0) / data.databases.length)
            };
        } catch (error) {
            return {
                status: 'error',
                icon: '❌',
                healthy: 0,
                total: 0,
                avgResponseTime: 0
            };
        }
    }

    async fetchReplicationStatus() {
        try {
            const response = await fetch('/api/replication/discover');
            const data = await response.json();
            const activeStreams = [...data.logical_streams, ...data.physical_streams].filter(s => s.status === 'active');
            const avgLag = activeStreams.length > 0 
                ? Math.round(activeStreams.reduce((sum, s) => sum + (s.lag_seconds * 1000), 0) / activeStreams.length)
                : 0;
            
            return {
                status: activeStreams.length === data.total_streams ? 'healthy' : 'warning',
                icon: activeStreams.length === data.total_streams ? '✅' : '⚠️',
                active: activeStreams.length,
                total: data.total_streams,
                avgLag
            };
        } catch (error) {
            return {
                status: 'error',
                icon: '❌',
                active: 0,
                total: 0,
                avgLag: 0
            };
        }
    }

    async loadRecentActivity() {
        // Placeholder for recent activity
        const activityContainer = document.getElementById('recent-activity');
        if (activityContainer) {
            activityContainer.innerHTML = `
                <div class="text-muted">
                    <div>• Replication discovery completed at ${new Date().toLocaleTimeString()}</div>
                    <div>• Database health check passed at ${new Date(Date.now() - 60000).toLocaleTimeString()}</div>
                    <div>• System startup completed at ${new Date(Date.now() - 300000).toLocaleTimeString()}</div>
                </div>
            `;
        }
    }

    async loadTopologyVisualization() {
        try {
            const response = await fetch('/api/replication/topology');
            const data = await response.json();
            
            // Initialize topology visualization if not already done
            if (!this.topologyViz) {
                this.topologyViz = new TopologyVisualization('topology-container');
            }
            
            // Load topology data
            await this.topologyViz.loadTopology();
            
            // Update databases and streams lists
            this.updateDatabasesList(data.databases);
            this.updateStreamsList(data.streams);
            
        } catch (error) {
            console.error('Error loading topology:', error);
            document.getElementById('topology-container').innerHTML = `
                <div class="text-center p-4">
                    <div class="status error">
                        <span>⚠️</span>
                        Error loading topology: ${error.message}
                    </div>
                </div>
            `;
        }
    }

    renderTopologyGraph(data) {
        const container = document.getElementById('topology-container');
        
        // Simple topology visualization (would be enhanced with D3.js)
        const nodes = data.topology_map.nodes;
        const edges = data.topology_map.edges;
        
        let html = '<div class="p-3"><h5>Topology Graph</h5>';
        
        // Simple text-based representation for now
        nodes.forEach(node => {
            const connections = edges.filter(e => e.source === node.id || e.target === node.id);
            html += `
                <div class="mb-2 p-2 border rounded">
                    <strong>${node.name}</strong> (${node.role})
                    <br><small>${node.host}:${node.port}</small>
                    <br><small>Connections: ${connections.length}</small>
                </div>
            `;
        });
        
        html += '</div>';
        container.innerHTML = html;
    }

    updateDatabasesList(databases) {
        const container = document.getElementById('databases-list');
        if (!container) return;
        
        let html = '';
        databases.forEach(db => {
            html += `
                <div class="mb-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${db.name}</strong>
                            <br><small>${db.host}:${db.port}</small>
                        </div>
                        <div class="status ${db.role === 'primary' ? 'info' : 'healthy'}">
                            ${db.role}
                        </div>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html || '<div class="text-muted">No databases found</div>';
    }

    updateStreamsList(streams) {
        const container = document.getElementById('streams-list');
        if (!container) return;
        
        let html = '';
        streams.forEach(stream => {
            html += `
                <div class="mb-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${stream.type} replication</strong>
                            <br><small>Lag: ${stream.lag_seconds}s</small>
                        </div>
                        <div class="status ${stream.status === 'active' ? 'healthy' : 'warning'}">
                            ${stream.status}
                        </div>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html || '<div class="text-muted">No replication streams found</div>';
    }

    async loadDatabasesTable() {
        try {
            const response = await fetch('/api/databases/test');
            const data = await response.json();
            
            let html = `
                <table class="table">
                    <thead>
                        <tr>
                            <th>Database ID</th>
                            <th>Status</th>
                            <th>Response Time</th>
                            <th>Version</th>
                            <th>Last Check</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            data.databases.forEach(db => {
                html += `
                    <tr>
                        <td><code>${db.database_id}</code></td>
                        <td>
                            <div class="status ${db.is_healthy ? 'healthy' : 'error'}">
                                ${db.is_healthy ? '✅ Healthy' : '❌ Error'}
                            </div>
                        </td>
                        <td>${db.response_time_ms.toFixed(2)}ms</td>
                        <td>${db.server_version}</td>
                        <td>${new Date(db.last_check).toLocaleString()}</td>
                        <td>
                            <button class="btn btn-outline-primary btn-sm" onclick="replicationManager.testDatabase('${db.database_id}')">
                                Test
                            </button>
                        </td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
            
            document.getElementById('databases-table').innerHTML = html;
            
        } catch (error) {
            document.getElementById('databases-table').innerHTML = `
                <div class="status error">
                    <span>⚠️</span>
                    Error loading databases: ${error.message}
                </div>
            `;
        }
    }

    async loadReplicationStreams() {
        try {
            const response = await fetch('/api/replication/discover');
            const data = await response.json();
            
            const allStreams = [...data.logical_streams, ...data.physical_streams];
            
            let html = `
                <table class="table">
                    <thead>
                        <tr>
                            <th>Stream ID</th>
                            <th>Type</th>
                            <th>Source → Target</th>
                            <th>Status</th>
                            <th>Lag</th>
                            <th>Last Sync</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            allStreams.forEach(stream => {
                html += `
                    <tr>
                        <td><code>${stream.id.substring(0, 8)}...</code></td>
                        <td>
                            <div class="status info">
                                ${stream.type}
                            </div>
                        </td>
                        <td>${stream.source_db_id.substring(0, 8)}... → ${stream.target_db_id.substring(0, 8)}...</td>
                        <td>
                            <div class="status ${stream.status === 'active' ? 'healthy' : 'warning'}">
                                ${stream.status}
                            </div>
                        </td>
                        <td>${stream.lag_seconds}s</td>
                        <td>${stream.last_sync_time ? new Date(stream.last_sync_time).toLocaleString() : 'Never'}</td>
                        <td>
                            <button class="btn btn-outline-primary btn-sm" onclick="replicationManager.viewStreamMetrics('${stream.id}')">
                                Metrics
                            </button>
                        </td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
            
            if (allStreams.length === 0) {
                html = '<div class="text-muted text-center p-4">No replication streams found</div>';
            }
            
            document.getElementById('replication-streams').innerHTML = html;
            
        } catch (error) {
            document.getElementById('replication-streams').innerHTML = `
                <div class="status error">
                    <span>⚠️</span>
                    Error loading replication streams: ${error.message}
                </div>
            `;
        }
    }

    async loadMigrationHistory() {
        try {
            const response = await fetch('/api/migrations/history');
            const data = await response.json();
            
            const container = document.getElementById('migration-history');
            if (!container) return;
            
            if (data.migrations && data.migrations.length > 0) {
                let html = `
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Execution ID</th>
                                <th>Executed By</th>
                                <th>Executed At</th>
                                <th>Databases</th>
                                <th>Success Rate</th>
                                <th>Execution Time</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                `;
                
                data.migrations.forEach(migration => {
                    const successRate = migration.total_databases > 0 
                        ? Math.round((migration.successful_databases / migration.total_databases) * 100)
                        : 0;
                    
                    html += `
                        <tr>
                            <td><code>${migration.execution_id.substring(0, 8)}...</code></td>
                            <td>${migration.executed_by}</td>
                            <td>${new Date(migration.executed_at).toLocaleString()}</td>
                            <td>${migration.successful_databases}/${migration.total_databases}</td>
                            <td>
                                <div class="status ${migration.success ? 'healthy' : 'error'}">
                                    ${successRate}%
                                </div>
                            </td>
                            <td>${Math.round(migration.execution_time_ms)}ms</td>
                            <td>
                                <div class="status ${migration.success ? 'healthy' : 'error'}">
                                    ${migration.success ? 'Success' : 'Failed'}
                                </div>
                            </td>
                        </tr>
                    `;
                });
                
                html += '</tbody></table>';
                container.innerHTML = html;
            } else {
                container.innerHTML = `
                    <div class="text-muted text-center p-4">
                        No migration history available yet
                    </div>
                `;
            }
            
        } catch (error) {
            const container = document.getElementById('migration-history');
            if (container) {
                container.innerHTML = `
                    <div class="status error">
                        <span>⚠️</span>
                        Error loading migration history: ${error.message}
                    </div>
                `;
            }
        }
    }

    loadSampleMigration() {
        const sampleSQL = `-- Sample Migration: Create Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Insert sample data
INSERT INTO users (username, email, full_name) 
VALUES 
    ('admin', 'admin@example.com', 'System Administrator'),
    ('user1', 'user1@example.com', 'Test User 1')
ON CONFLICT (username) DO NOTHING;`;

        document.getElementById('migration-sql').value = sampleSQL;
    }

    clearMigrationEditor() {
        document.getElementById('migration-sql').value = '';
        document.getElementById('migration-results').innerHTML = '<div class="text-muted">Migration results will appear here...</div>';
        this.hideMigrationProgress();
    }

    async validateMigration() {
        const sqlScript = document.getElementById('migration-sql').value.trim();
        
        if (!sqlScript) {
            alert('Please enter a SQL script to validate');
            return;
        }

        try {
            const response = await fetch('/api/migrations/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    sql_script: sqlScript,
                    dry_run: true
                })
            });

            const result = await response.json();
            
            if (result.success) {
                const validation = result.validation_results;
                let output = `<div class="status healthy">✓ Validation Successful</div><br>`;
                output += `<strong>Statement Count:</strong> ${validation.statement_count}<br>`;
                output += `<strong>Target Databases:</strong> ${validation.target_databases}<br>`;
                output += `<strong>Estimated Time:</strong> ${validation.estimated_execution_time}<br><br>`;
                
                if (validation.warnings.length > 0) {
                    output += `<div class="status warning">⚠️ Warnings:</div>`;
                    validation.warnings.forEach(warning => {
                        output += `<div class="text-warning">• ${warning}</div>`;
                    });
                }
                
                if (validation.errors.length > 0) {
                    output += `<div class="status error">❌ Errors:</div>`;
                    validation.errors.forEach(error => {
                        output += `<div class="text-danger">• ${error}</div>`;
                    });
                }
                
                document.getElementById('migration-results').innerHTML = output;
            } else {
                document.getElementById('migration-results').innerHTML = `
                    <div class="status error">❌ Validation Failed</div><br>
                    ${result.message}
                `;
            }

        } catch (error) {
            document.getElementById('migration-results').innerHTML = `
                <div class="status error">❌ Validation Error</div><br>
                ${error.message}
            `;
        }
    }

    async executeMigration() {
        const sqlScript = document.getElementById('migration-sql').value.trim();
        
        if (!sqlScript) {
            alert('Please enter a SQL script to execute');
            return;
        }

        const dryRun = document.getElementById('dry-run-checkbox').checked;
        const rollbackOnError = document.getElementById('rollback-checkbox').checked;

        if (!dryRun && !confirm('Are you sure you want to execute this migration? This will modify your databases.')) {
            return;
        }

        try {
            // Show progress
            this.showMigrationProgress();
            this.updateMigrationStatus('Starting migration execution...');
            
            const executeBtn = document.getElementById('execute-btn');
            const executeIcon = document.getElementById('execute-icon');
            executeBtn.disabled = true;
            executeIcon.textContent = '⏳';

            const response = await fetch('/api/migrations/execute', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    sql_script: sqlScript,
                    dry_run: dryRun,
                    rollback_on_error: rollbackOnError,
                    execution_order: 'sequential'
                })
            });

            const result = await response.json();
            
            // Display results
            let output = `<div class="status ${result.success ? 'healthy' : 'error'}">
                ${result.success ? '✅' : '❌'} ${result.message}
            </div><br>`;
            
            output += `<strong>Execution Summary:</strong><br>`;
            output += `• Total Databases: ${result.total_databases}<br>`;
            output += `• Successful: ${result.successful_databases}<br>`;
            output += `• Failed: ${result.failed_databases}<br>`;
            output += `• Execution Time: ${Math.round(result.execution_time_ms)}ms<br>`;
            
            if (result.rollback_performed) {
                output += `• <span class="text-warning">Rollback Performed</span><br>`;
            }
            
            output += `<br><strong>Database Results:</strong><br>`;
            
            result.results.forEach(dbResult => {
                output += `<div class="mb-2 p-2 border-left" style="border-left: 3px solid ${dbResult.success ? '#28a745' : '#dc3545'};">`;
                output += `<strong>${dbResult.database_name}</strong><br>`;
                output += `Status: ${dbResult.success ? 'Success' : 'Failed'}<br>`;
                output += `Time: ${Math.round(dbResult.execution_time_ms)}ms<br>`;
                
                if (dbResult.rows_affected !== null) {
                    output += `Rows Affected: ${dbResult.rows_affected}<br>`;
                }
                
                if (dbResult.error_message) {
                    output += `<span class="text-danger">Error: ${dbResult.error_message}</span><br>`;
                }
                
                output += `</div>`;
            });
            
            document.getElementById('migration-results').innerHTML = output;
            
            // Update migration history
            await this.loadMigrationHistory();
            
            this.updateMigrationStatus(result.success ? 'Migration completed successfully' : 'Migration failed');
            
        } catch (error) {
            document.getElementById('migration-results').innerHTML = `
                <div class="status error">❌ Execution Error</div><br>
                ${error.message}
            `;
            this.updateMigrationStatus('Migration execution failed');
        } finally {
            // Reset button
            const executeBtn = document.getElementById('execute-btn');
            const executeIcon = document.getElementById('execute-icon');
            executeBtn.disabled = false;
            executeIcon.textContent = '▶️';
            
            this.hideMigrationProgress();
        }
    }

    showMigrationProgress() {
        const progressContainer = document.getElementById('migration-progress');
        if (progressContainer) {
            progressContainer.style.display = 'block';
            progressContainer.querySelector('.progress-bar').style.width = '0%';
        }
    }

    hideMigrationProgress() {
        const progressContainer = document.getElementById('migration-progress');
        if (progressContainer) {
            progressContainer.style.display = 'none';
        }
    }

    updateMigrationProgress(percent) {
        const progressBar = document.querySelector('#migration-progress .progress-bar');
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
        }
    }

    updateMigrationStatus(message) {
        const statusContainer = document.getElementById('migration-status');
        if (statusContainer) {
            statusContainer.innerHTML = `<small class="text-muted">${message}</small>`;
        }
    }

    setupMigrationWebSocket() {
        // WebSocket setup for real-time migration progress
        // This would be implemented when we have an active migration execution
    }

    setupAutoRefresh() {
        // Auto-refresh dashboard every 30 seconds
        this.refreshInterval = setInterval(() => {
            if (this.currentPage === 'dashboard') {
                this.loadDashboard();
            }
        }, 30000);
    }

    // Utility methods
    async refreshTopology() {
        const icon = document.getElementById('refresh-icon');
        if (icon) {
            icon.style.animation = 'spin 1s linear infinite';
        }
        
        await this.loadTopologyVisualization();
        
        if (icon) {
            icon.style.animation = '';
        }
    }

    async testDatabase(databaseId) {
        try {
            const response = await fetch(`/api/databases/test/${databaseId}`);
            const data = await response.json();
            
            alert(`Database test result:\nStatus: ${data.is_healthy ? 'Healthy' : 'Error'}\nResponse time: ${data.response_time_ms}ms`);
        } catch (error) {
            alert(`Error testing database: ${error.message}`);
        }
    }

    async viewStreamMetrics(streamId) {
        try {
            const response = await fetch(`/api/replication/streams/${streamId}/metrics`);
            const data = await response.json();
            
            alert(`Stream metrics:\nLag: ${data.lag_seconds}s\nWAL Position: ${data.wal_position}\nSynced Tables: ${data.synced_tables}/${data.total_tables}`);
        } catch (error) {
            alert(`Error loading stream metrics: ${error.message}`);
        }
    }

    async loadDatabaseConfigsTable() {
        try {
            const response = await fetch('/api/database-config/');
            const data = await response.json();
            
            let html = `
                <table class="table">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Role</th>
                            <th>Host:Port</th>
                            <th>Database</th>
                            <th>Environment</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            if (data.database_configs && data.database_configs.length > 0) {
                data.database_configs.forEach(config => {
                    html += `
                        <tr>
                            <td><strong>${config.name}</strong></td>
                            <td>
                                <div class="status ${config.role === 'primary' ? 'info' : 'healthy'}">
                                    ${config.role}
                                </div>
                            </td>
                            <td>${config.host}:${config.port}</td>
                            <td>${config.database}</td>
                            <td>${config.environment}</td>
                            <td>
                                <div class="status info">
                                    <span id="status-${config.id}">Unknown</span>
                                </div>
                            </td>
                            <td>
                                <button class="btn btn-outline-primary btn-sm" onclick="replicationManager.testDatabaseConfig('${config.id}')">
                                    Test
                                </button>
                                <button class="btn btn-outline-secondary btn-sm" onclick="replicationManager.editDatabaseConfig('${config.id}')">
                                    Edit
                                </button>
                                <button class="btn btn-outline-danger btn-sm" onclick="replicationManager.deleteDatabaseConfig('${config.id}')">
                                    Delete
                                </button>
                            </td>
                        </tr>
                    `;
                });
            } else {
                html += `
                    <tr>
                        <td colspan="7" class="text-center text-muted">
                            No database configurations found. Click "Add Database" to create one.
                        </td>
                    </tr>
                `;
            }
            
            html += '</tbody></table>';
            
            document.getElementById('databases-table').innerHTML = html;
            
            // Test all configurations to get status
            if (data.database_configs && data.database_configs.length > 0) {
                data.database_configs.forEach(config => {
                    this.testDatabaseConfig(config.id, true);
                });
            }
            
        } catch (error) {
            document.getElementById('databases-table').innerHTML = `
                <div class="status error">
                    <span>⚠️</span>
                    Error loading database configurations: ${error.message}
                </div>
            `;
        }
    }

    showAddDatabaseModal() {
        document.getElementById('add-database-modal').style.display = 'flex';
    }

    hideAddDatabaseModal() {
        document.getElementById('add-database-modal').style.display = 'none';
        document.getElementById('add-database-form').reset();
    }

    async submitAddDatabase() {
        try {
            const form = document.getElementById('add-database-form');
            const formData = new FormData(form);
            
            const requestData = {
                name: formData.get('name'),
                host: formData.get('host'),
                port: parseInt(formData.get('port')),
                database: formData.get('database'),
                credentials_arn: formData.get('credentials_arn'),
                role: formData.get('role'),
                environment: formData.get('environment'),
                cloud_provider: formData.get('cloud_provider'),
                vpc_id: formData.get('vpc_id') || null,
                use_iam_auth: formData.has('use_iam_auth')
            };

            const response = await fetch('/api/database-config/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            const result = await response.json();

            if (result.success) {
                this.hideAddDatabaseModal();
                await this.loadDatabaseConfigsTable();
                alert('Database configuration added successfully!');
            } else {
                alert(`Error: ${result.message}`);
            }

        } catch (error) {
            alert(`Error adding database: ${error.message}`);
        }
    }

    async testDatabaseConfig(configId, silent = false) {
        try {
            const response = await fetch(`/api/database-config/${configId}/test`, {
                method: 'POST'
            });
            const result = await response.json();

            const statusElement = document.getElementById(`status-${configId}`);
            if (statusElement) {
                if (result.success) {
                    statusElement.textContent = 'Healthy';
                    statusElement.parentElement.className = 'status healthy';
                } else {
                    statusElement.textContent = 'Error';
                    statusElement.parentElement.className = 'status error';
                }
            }

            if (!silent) {
                if (result.success) {
                    alert(`Database test successful!\nResponse time: ${result.test_results.response_time_ms}ms\nServer version: ${result.test_results.server_version}`);
                } else {
                    alert(`Database test failed: ${result.message}`);
                }
            }

        } catch (error) {
            const statusElement = document.getElementById(`status-${configId}`);
            if (statusElement) {
                statusElement.textContent = 'Error';
                statusElement.parentElement.className = 'status error';
            }

            if (!silent) {
                alert(`Error testing database: ${error.message}`);
            }
        }
    }

    async deleteDatabaseConfig(configId) {
        if (!confirm('Are you sure you want to delete this database configuration?')) {
            return;
        }

        try {
            const response = await fetch(`/api/database-config/${configId}`, {
                method: 'DELETE'
            });
            const result = await response.json();

            if (result.success) {
                await this.loadDatabaseConfigsTable();
                alert('Database configuration deleted successfully!');
            } else {
                alert(`Error: ${result.message}`);
            }

        } catch (error) {
            alert(`Error deleting database: ${error.message}`);
        }
    }

    async testAllConnections() {
        const testButtons = document.querySelectorAll('[onclick*="testDatabaseConfig"]');
        testButtons.forEach(button => {
            const configId = button.getAttribute('onclick').match(/'([^']+)'/)[1];
            this.testDatabaseConfig(configId, true);
        });
    }

    loadInitialData() {
        // Load initial page based on URL parameter or default to dashboard
        const urlParams = new URLSearchParams(window.location.search);
        const page = urlParams.get('page') || 'dashboard';
        this.navigateTo(page);
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.replicationManager = new ReplicationManager();
});

// Handle browser back/forward buttons
window.addEventListener('popstate', (e) => {
    if (e.state && e.state.page) {
        window.replicationManager.navigateTo(e.state.page);
    }
});