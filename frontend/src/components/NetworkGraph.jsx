import React, { useRef, useEffect, useState } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, AlertCircle } from 'lucide-react';

export default function NetworkGraph({ data, onNodeClick }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
  const [hoveredNode, setHoveredNode] = useState(null);
  
  // Transform and viewport states
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const [draggedNode, setDraggedNode] = useState(null);

  // Initialize simulation nodes and links when new data is received
  useEffect(() => {
    if (!data || !data.nodes || data.nodes.length === 0) {
      setNodes([]);
      setLinks([]);
      return;
    }

    const width = containerRef.current?.clientWidth || 600;
    const height = containerRef.current?.clientHeight || 400;

    // Create a copy of the nodes and seed them around the center
    const simNodes = data.nodes.map((node) => {
      // Check if node already exists to preserve position
      const existing = nodes.find((n) => n.id === node.id);
      return {
        ...node,
        x: existing ? existing.x : width / 2 + (Math.random() - 0.5) * 150,
        y: existing ? existing.y : height / 2 + (Math.random() - 0.5) * 150,
        vx: 0,
        vy: 0,
        radius: node.type === 'case' ? 14 : node.type === 'accused' ? 12 : 10
      };
    });

    // Create a copy of links mapped to node objects
    const simLinks = data.edges.map((edge) => {
      const sourceNode = simNodes.find((n) => n.id === edge.source);
      const targetNode = simNodes.find((n) => n.id === edge.target);
      return {
        ...edge,
        sourceNode,
        targetNode
      };
    });

    setNodes(simNodes);
    setLinks(simLinks);
    // Reset pan/zoom
    setTransform({ x: 0, y: 0, k: 1 });
  }, [data]);

  // Run the force-directed simulation loop
  useEffect(() => {
    if (nodes.length === 0) return;

    let animationFrameId;
    const width = containerRef.current?.clientWidth || 600;
    const height = containerRef.current?.clientHeight || 400;

    const runSimulation = () => {
      // 1. Repulsion (Coulomb-like repulsion between all nodes)
      for (let i = 0; i < nodes.length; i++) {
        const nodeA = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const nodeB = nodes[j];
          const dx = nodeB.x - nodeA.x;
          const dy = nodeB.y - nodeA.y;
          const distSq = dx * dx + dy * dy + 0.1;
          const dist = Math.sqrt(distSq);

          if (dist < 280) {
            // Repulsion strength
            const force = (0.6 * (280 - dist)) / dist;
            const fx = dx * force * 0.05;
            const fy = dy * force * 0.05;

            if (nodeA !== draggedNode) {
              nodeA.vx -= fx;
              nodeA.vy -= fy;
            }
            if (nodeB !== draggedNode) {
              nodeB.vx += fx;
              nodeB.vy += fy;
            }
          }
        }
      }

      // 2. Attraction (Spring-like attraction between connected nodes)
      links.forEach((link) => {
        if (!link.sourceNode || !link.targetNode) return;
        const nodeA = link.sourceNode;
        const nodeB = link.targetNode;
        const dx = nodeB.x - nodeA.x;
        const dy = nodeB.y - nodeA.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
        
        // Target link length
        const targetLen = 80;
        const force = (dist - targetLen) * 0.03;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (nodeA !== draggedNode) {
          nodeA.vx += fx;
          nodeA.vy += fy;
        }
        if (nodeB !== draggedNode) {
          nodeB.vx -= fx;
          nodeB.vy -= fy;
        }
      });

      // 3. Gravity & Friction (Pull to center and slow down velocity)
      const centerX = width / 2;
      const centerY = height / 2;
      nodes.forEach((node) => {
        if (node === draggedNode) return;

        // Center gravity
        node.vx += (centerX - node.x) * 0.008;
        node.vy += (centerY - node.y) * 0.008;

        // Friction / drag
        node.vx *= 0.85;
        node.vy *= 0.85;

        // Update positions
        node.x += node.vx;
        node.y += node.vy;
      });

      // 4. Render on Canvas
      drawCanvas();
      
      animationFrameId = requestAnimationFrame(runSimulation);
    };

    const drawCanvas = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      ctx.save();
      // Apply panning and zooming transforms
      ctx.translate(transform.x, transform.y);
      ctx.scale(transform.k, transform.k);

      // Draw Edges
      links.forEach((link) => {
        if (!link.sourceNode || !link.targetNode) return;
        ctx.beginPath();
        ctx.moveTo(link.sourceNode.x, link.sourceNode.y);
        ctx.lineTo(link.targetNode.x, link.targetNode.y);
        
        // Edge styling
        if (link.relation === 'shared_contact') {
          ctx.strokeStyle = '#f43f5e';
          ctx.lineWidth = 1.5;
          ctx.setLineDash([4, 4]); // Dashed line for shared contacts
        } else {
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
          ctx.lineWidth = 1.0;
          ctx.setLineDash([]);
        }
        ctx.stroke();

        // Draw Edge Label occasionally or mid-point
        const midX = (link.sourceNode.x + link.targetNode.x) / 2;
        const midY = (link.sourceNode.y + link.targetNode.y) / 2;
        ctx.fillStyle = 'rgba(156, 163, 175, 0.4)';
        ctx.font = '8px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(link.relation, midX, midY - 4);
      });
      ctx.setLineDash([]); // Reset line dash

      // Draw Nodes
      nodes.forEach((node) => {
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, 2 * Math.PI);
        
        // Colors & Glow
        let color = '#ffffff';
        let glowColor = 'rgba(255,255,255,0.2)';
        if (node.type === 'case') {
          color = '#00c6ff';
          glowColor = 'rgba(0, 198, 255, 0.4)';
        } else if (node.type === 'accused') {
          color = '#ff5e62';
          glowColor = 'rgba(255, 94, 98, 0.4)';
        } else if (node.type === 'location') {
          color = '#00f260';
          glowColor = 'rgba(0, 242, 96, 0.4)';
        }

        ctx.fillStyle = color;
        ctx.shadowColor = glowColor;
        ctx.shadowBlur = hoveredNode?.id === node.id ? 15 : 6;
        ctx.fill();
        ctx.shadowBlur = 0; // Reset shadow

        // Outline hovered node
        if (hoveredNode?.id === node.id) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2.0;
          ctx.stroke();
        } else {
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
          ctx.lineWidth = 1.0;
          ctx.stroke();
        }

        // Labels
        ctx.fillStyle = hoveredNode?.id === node.id ? '#ffffff' : 'rgba(243, 244, 246, 0.85)';
        ctx.font = hoveredNode?.id === node.id ? 'bold 11px Inter' : '10px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(node.label, node.x, node.y + node.radius + 14);
      });

      ctx.restore();
    };

    // Run simulation frame
    animationFrameId = requestAnimationFrame(runSimulation);

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [nodes, links, transform, hoveredNode, draggedNode]);

  // Set canvas resolution on resize
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
    };
    
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Screen-to-Canvas coord conversion
  const getCanvasCoords = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;

    // Inverse transform
    const x = (screenX - transform.x) / transform.k;
    const y = (screenY - transform.y) / transform.k;
    return { x, y };
  };

  const handleMouseDown = (e) => {
    const coords = getCanvasCoords(e);
    
    // Check if clicked a node (within radius)
    const clickedNode = nodes.find((node) => {
      const dx = node.x - coords.x;
      const dy = node.y - coords.y;
      return dx * dx + dy * dy <= (node.radius + 5) * (node.radius + 5);
    });

    if (clickedNode) {
      setDraggedNode(clickedNode);
    } else {
      setIsPanning(true);
      setPanStart({ x: e.clientX - transform.x, y: e.clientY - transform.y });
    }
  };

  const handleMouseMove = (e) => {
    const coords = getCanvasCoords(e);
    
    // Check if hovering a node
    const hovering = nodes.find((node) => {
      const dx = node.x - coords.x;
      const dy = node.y - coords.y;
      return dx * dx + dy * dy <= (node.radius + 5) * (node.radius + 5);
    });
    setHoveredNode(hovering || null);

    if (draggedNode) {
      draggedNode.x = coords.x;
      draggedNode.y = coords.y;
      draggedNode.vx = 0;
      draggedNode.vy = 0;
    } else if (isPanning) {
      setTransform((prev) => ({
        ...prev,
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y
      }));
    }
  };

  const handleMouseUp = () => {
    setDraggedNode(null);
    setIsPanning(false);
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const scaleFactor = 1.05;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoom = e.deltaY < 0 ? scaleFactor : 1 / scaleFactor;
    const newK = Math.max(0.2, Math.min(4, transform.k * zoom));

    // Zoom centered on mouse
    setTransform((prev) => ({
      x: mouseX - (mouseX - prev.x) * (newK / prev.k),
      y: mouseY - (mouseY - prev.y) * (newK / prev.k),
      k: newK
    }));
  };

  const handleDoubleClick = (e) => {
    const coords = getCanvasCoords(e);
    const clickedNode = nodes.find((node) => {
      const dx = node.x - coords.x;
      const dy = node.y - coords.y;
      return dx * dx + dy * dy <= (node.radius + 5) * (node.radius + 5);
    });

    if (clickedNode && onNodeClick) {
      onNodeClick(clickedNode);
    }
  };

  const zoom = (direction) => {
    const factor = direction === 'in' ? 1.25 : 0.8;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const midX = canvas.width / 2;
    const midY = canvas.height / 2;
    const newK = Math.max(0.2, Math.min(4, transform.k * factor));

    setTransform((prev) => ({
      x: midX - (midX - prev.x) * (newK / prev.k),
      y: midY - (midY - prev.y) * (newK / prev.k),
      k: newK
    }));
  };

  const resetTransform = () => {
    setTransform({ x: 0, y: 0, k: 1 });
  };

  if (!data || !data.nodes || data.nodes.length === 0) {
    return (
      <div className="placeholder-view">
        <AlertCircle size={40} className="placeholder-icon" />
        <h3>No Network Graph Available</h3>
        <p>Perform a connection or accomplice search to visualize relationships between cases, accused, and locations.</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="network-graph-container">
      <canvas
        ref={canvasRef}
        className="graph-canvas"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        onDoubleClick={handleDoubleClick}
      />

      {/* Control Buttons */}
      <div style={{ position: 'absolute', top: '16px', right: '16px', display: 'flex', flexDirection: 'column', gap: '8px', zIndex: 10 }}>
        <button className="btn-secondary" style={{ padding: '8px' }} onClick={() => zoom('in')} title="Zoom In">
          <ZoomIn size={16} />
        </button>
        <button className="btn-secondary" style={{ padding: '8px' }} onClick={() => zoom('out')} title="Zoom Out">
          <ZoomOut size={16} />
        </button>
        <button className="btn-secondary" style={{ padding: '8px' }} onClick={resetTransform} title="Reset View">
          <RotateCcw size={16} />
        </button>
      </div>

      {/* Graph Legend */}
      <div className="graph-legend">
        <div className="legend-item">
          <div className="legend-color accused" />
          <span>Accused / Suspect</span>
        </div>
        <div className="legend-item">
          <div className="legend-color case" />
          <span>FIR Case Record</span>
        </div>
        <div className="legend-item">
          <div className="legend-color location" />
          <span>Crime Location</span>
        </div>
      </div>
    </div>
  );
}
