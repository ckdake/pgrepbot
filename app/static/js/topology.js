// PostgreSQL Replication Manager - Topology Visualization

class TopologyVisualization {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.width = 800;
        this.height = 500;
        this.svg = null;
        this.simulation = null;
        this.nodes = [];
        this.links = [];
        
        this.init();
    }

    init() {
        // Clear container
        this.container.innerHTML = '';
        
        // Create SVG
        this.svg = d3.select(`#${this.containerId}`)
            .append('svg')
            .attr('width', '100%')
            .attr('height', this.height)
            .attr('viewBox', `0 0 ${this.width} ${this.height}`)
            .style('border', '1px solid #dee2e6')
            .style('border-radius', '4px')
            .style('background', '#f8f9fa');

        // Add zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.5, 3])
            .on('zoom', (event) => {
                this.svg.select('.topology-group')
                    .attr('transform', event.transform);
            });

        this.svg.call(zoom);

        // Create main group for topology elements
        this.topologyGroup = this.svg.append('g')
            .attr('class', 'topology-group');

        // Add arrow markers for directed edges
        this.svg.append('defs').selectAll('marker')
            .data(['replication'])
            .enter().append('marker')
            .attr('id', d => d)
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 25)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-5L10,0L0,5')
            .attr('fill', '#667eea');

        // Initialize force simulation
        this.simulation = d3.forceSimulation()
            .force('link', d3.forceLink().id(d => d.id).distance(150))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('center', d3.forceCenter(this.width / 2, this.height / 2))
            .force('collision', d3.forceCollide().radius(50));
    }

    async loadTopology() {
        try {
            const response = await fetch('/api/replication/topology');
            const data = await response.json();
            
            this.renderTopology(data);
            
        } catch (error) {
            console.error('Error loading topology:', error);
            this.showError('Failed to load topology data');
        }
    }

    renderTopology(data) {
        // Prepare nodes and links
        this.nodes = data.topology_map.nodes.map(node => ({
            ...node,
            x: Math.random() * this.width,
            y: Math.random() * this.height
        }));

        this.links = data.topology_map.edges.map(edge => ({
            ...edge,
            source: edge.source,
            target: edge.target
        }));

        // Update simulation
        this.simulation
            .nodes(this.nodes)
            .force('link').links(this.links);

        // Render links
        const link = this.topologyGroup.selectAll('.link')
            .data(this.links)
            .enter().append('line')
            .attr('class', 'link')
            .attr('stroke', d => this.getLinkColor(d))
            .attr('stroke-width', 3)
            .attr('marker-end', 'url(#replication)')
            .style('opacity', 0.8);

        // Add link labels
        const linkLabel = this.topologyGroup.selectAll('.link-label')
            .data(this.links)
            .enter().append('text')
            .attr('class', 'link-label')
            .attr('text-anchor', 'middle')
            .attr('font-size', '10px')
            .attr('fill', '#666')
            .text(d => `${d.type} (${d.lag_seconds}s)`);

        // Render nodes
        const node = this.topologyGroup.selectAll('.node')
            .data(this.nodes)
            .enter().append('g')
            .attr('class', 'node')
            .call(d3.drag()
                .on('start', (event, d) => this.dragStarted(event, d))
                .on('drag', (event, d) => this.dragged(event, d))
                .on('end', (event, d) => this.dragEnded(event, d)));

        // Add node circles
        node.append('circle')
            .attr('r', 25)
            .attr('fill', d => this.getNodeColor(d))
            .attr('stroke', '#fff')
            .attr('stroke-width', 2)
            .style('cursor', 'pointer');

        // Add node icons
        node.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '0.3em')
            .attr('font-size', '16px')
            .text(d => this.getNodeIcon(d));

        // Add node labels
        node.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '45px')
            .attr('font-size', '12px')
            .attr('font-weight', 'bold')
            .attr('fill', '#333')
            .text(d => d.name);

        // Add node details
        node.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '58px')
            .attr('font-size', '10px')
            .attr('fill', '#666')
            .text(d => `${d.host}:${d.port}`);

        // Add tooltips
        node.append('title')
            .text(d => `${d.name}\n${d.role}\n${d.host}:${d.port}\nEnvironment: ${d.environment}`);

        // Update positions on simulation tick
        this.simulation.on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            linkLabel
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2);

            node
                .attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Add legend
        this.addLegend();

        // Add statistics
        this.addStatistics(data.topology_map.summary);
    }

    getNodeColor(node) {
        switch (node.role) {
            case 'primary':
                return '#28a745'; // Green
            case 'replica':
                return '#17a2b8'; // Blue
            default:
                return '#6c757d'; // Gray
        }
    }

    getNodeIcon(node) {
        switch (node.role) {
            case 'primary':
                return '🗄️'; // Database icon for primary
            case 'replica':
                return '📋'; // Copy icon for replica
            default:
                return '💾'; // Disk icon for others
        }
    }

    getLinkColor(link) {
        switch (link.status) {
            case 'active':
                return '#28a745'; // Green
            case 'inactive':
                return '#dc3545'; // Red
            case 'warning':
                return '#ffc107'; // Yellow
            default:
                return '#6c757d'; // Gray
        }
    }

    addLegend() {
        const legend = this.svg.append('g')
            .attr('class', 'legend')
            .attr('transform', 'translate(20, 20)');

        const legendData = [
            { color: '#28a745', label: 'Primary Database', icon: '🗄️' },
            { color: '#17a2b8', label: 'Replica Database', icon: '📋' },
            { color: '#28a745', label: 'Active Replication', type: 'line' },
            { color: '#dc3545', label: 'Inactive Replication', type: 'line' }
        ];

        const legendItems = legend.selectAll('.legend-item')
            .data(legendData)
            .enter().append('g')
            .attr('class', 'legend-item')
            .attr('transform', (d, i) => `translate(0, ${i * 25})`);

        // Add legend background
        legend.insert('rect', ':first-child')
            .attr('x', -10)
            .attr('y', -10)
            .attr('width', 200)
            .attr('height', legendData.length * 25 + 10)
            .attr('fill', 'rgba(255, 255, 255, 0.9)')
            .attr('stroke', '#dee2e6')
            .attr('rx', 4);

        legendItems.each(function(d) {
            const item = d3.select(this);
            
            if (d.type === 'line') {
                item.append('line')
                    .attr('x1', 0)
                    .attr('y1', 8)
                    .attr('x2', 20)
                    .attr('y2', 8)
                    .attr('stroke', d.color)
                    .attr('stroke-width', 3);
            } else {
                item.append('circle')
                    .attr('cx', 10)
                    .attr('cy', 8)
                    .attr('r', 8)
                    .attr('fill', d.color);
                
                item.append('text')
                    .attr('x', 10)
                    .attr('y', 12)
                    .attr('text-anchor', 'middle')
                    .attr('font-size', '10px')
                    .text(d.icon);
            }
            
            item.append('text')
                .attr('x', 30)
                .attr('y', 12)
                .attr('font-size', '12px')
                .attr('fill', '#333')
                .text(d.label);
        });
    }

    addStatistics(summary) {
        const stats = this.svg.append('g')
            .attr('class', 'statistics')
            .attr('transform', `translate(${this.width - 200}, 20)`);

        // Add statistics background
        stats.append('rect')
            .attr('x', -10)
            .attr('y', -10)
            .attr('width', 180)
            .attr('height', 120)
            .attr('fill', 'rgba(255, 255, 255, 0.9)')
            .attr('stroke', '#dee2e6')
            .attr('rx', 4);

        // Add title
        stats.append('text')
            .attr('x', 0)
            .attr('y', 10)
            .attr('font-size', '14px')
            .attr('font-weight', 'bold')
            .attr('fill', '#333')
            .text('Topology Summary');

        // Add statistics
        const statsData = [
            { label: 'Total Databases', value: summary.total_databases },
            { label: 'Total Streams', value: summary.total_streams },
            { label: 'Logical Streams', value: summary.logical_streams },
            { label: 'Physical Streams', value: summary.physical_streams },
            { label: 'Active Streams', value: summary.active_streams }
        ];

        stats.selectAll('.stat-item')
            .data(statsData)
            .enter().append('text')
            .attr('class', 'stat-item')
            .attr('x', 0)
            .attr('y', (d, i) => 30 + i * 18)
            .attr('font-size', '12px')
            .attr('fill', '#666')
            .text(d => `${d.label}: ${d.value}`);
    }

    showError(message) {
        this.container.innerHTML = `
            <div class="text-center p-4">
                <div class="status error">
                    <span>⚠️</span>
                    ${message}
                </div>
            </div>
        `;
    }

    // Drag event handlers
    dragStarted(event, d) {
        if (!event.active) this.simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    dragEnded(event, d) {
        if (!event.active) this.simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }

    // Public methods
    refresh() {
        this.loadTopology();
    }

    resize() {
        const containerRect = this.container.getBoundingClientRect();
        this.width = containerRect.width;
        this.svg.attr('viewBox', `0 0 ${this.width} ${this.height}`);
        this.simulation.force('center', d3.forceCenter(this.width / 2, this.height / 2));
        this.simulation.alpha(0.3).restart();
    }
}

// Make TopologyVisualization available globally
window.TopologyVisualization = TopologyVisualization;