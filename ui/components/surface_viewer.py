"""
Interactive Three.js viewer for Surface-on-Bed feature.

Creates an HTML component that:
- Renders the 3D model with Three.js (STLLoader)
- Highlights detected flat face groups in distinct colors
- On face click: updates a hidden Gradio textbox with {group_index, normal}
  so that Python can rotate the model accordingly
"""

from __future__ import annotations

import base64
import json
import os
from typing import List

# Colours used to highlight face groups (cycling)
_FACE_COLORS = [
    "#FF6B6B",  # red
    "#4ECDC4",  # teal
    "#45B7D1",  # blue
    "#96CEB4",  # green
    "#FECA57",  # yellow
    "#FF9FF3",  # pink
    "#54A0FF",  # sky blue
    "#5F27CD",  # purple
    "#00D2D3",  # cyan
    "#FF9F43",  # orange
    "#C8D6E5",  # light grey
    "#8395A7",  # grey
]

_VIEWER_TEMPLATE = """\
<div id="sob-container-{uid}" style="
    position: relative;
    width: 100%;
    height: 480px;
    background: #1a1a2e;
    border-radius: 8px;
    overflow: hidden;
    font-family: sans-serif;
">
  <canvas id="sob-canvas-{uid}" style="width:100%;height:100%;display:block;"></canvas>
  <div id="sob-info-{uid}" style="
      position: absolute; top:10px; left:10px;
      background: rgba(0,0,0,0.6);
      color: #fff; padding: 8px 12px;
      border-radius: 6px; font-size: 13px;
      pointer-events: none;
  ">Кликните на выделенную грань</div>
  <div id="sob-legend-{uid}" style="
      position: absolute; top:10px; right:10px;
      background: rgba(0,0,0,0.6);
      color: #fff; padding: 8px 12px;
      border-radius: 6px; font-size: 12px;
      max-height: 380px; overflow-y: auto;
  "></div>
</div>
<script>
(function() {{
  // Prevent double-init on Gradio re-renders
  var uid = '{uid}';
  if (window['_sob_init_' + uid]) return;
  window['_sob_init_' + uid] = true;

  // --- Data injected from Python ---
  var STL_B64 = '{stl_b64}';
  var FACE_GROUPS = {face_groups_json};

  // --- Load Three.js and STLLoader lazily ---
  function loadScript(src, cb) {{
    if (document.querySelector('script[src="' + src + '"]')) {{ cb(); return; }}
    var s = document.createElement('script');
    s.src = src; s.onload = cb; document.head.appendChild(s);
  }}

  var THREE_CDN = 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js';
  var STL_CDN  = 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/STLLoader.js';

  loadScript(THREE_CDN, function() {{
    // STLLoader must be loaded as a module-ish shim
    initViewer();
  }});

  function initViewer() {{
    var THREE = window.THREE;
    if (!THREE) {{ setTimeout(initViewer, 100); return; }}

    var canvas    = document.getElementById('sob-canvas-' + uid);
    var infoEl    = document.getElementById('sob-info-' + uid);
    var legendEl  = document.getElementById('sob-legend-' + uid);
    if (!canvas) return;

    // Renderer
    var renderer = new THREE.WebGLRenderer({{ canvas: canvas, antialias: true }});
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setClearColor(0x1a1a2e);

    // Scene
    var scene  = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 10000);

    // Lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    var dl = new THREE.DirectionalLight(0xffffff, 0.8);
    dl.position.set(1, 2, 3); scene.add(dl);

    // Orbit controls (manual simple version)
    var isDragging = false, lastX = 0, lastY = 0;
    var rotX = 0, rotY = 0, zoom = 1;
    canvas.addEventListener('mousedown', function(e) {{ isDragging=true; lastX=e.clientX; lastY=e.clientY; }});
    window.addEventListener('mouseup',   function()  {{ isDragging=false; }});
    canvas.addEventListener('mousemove', function(e) {{
      if (!isDragging) return;
      rotY += (e.clientX - lastX) * 0.005;
      rotX += (e.clientY - lastY) * 0.005;
      lastX = e.clientX; lastY = e.clientY;
    }});
    canvas.addEventListener('wheel', function(e) {{
      zoom *= (1 + e.deltaY * 0.001);
      zoom = Math.max(0.1, Math.min(zoom, 10));
      e.preventDefault();
    }}, {{ passive: false }});

    // Decode STL from base64
    var raw = atob(STL_B64);
    var buf = new Uint8Array(raw.length);
    for (var i=0; i<raw.length; i++) buf[i] = raw.charCodeAt(i);

    // Parse STL manually (binary)
    var ab = buf.buffer;
    var view = new DataView(ab);
    var numTri = view.getUint32(80, true);
    var positions = [];
    var normals   = [];
    for (var t=0; t<numTri; t++) {{
      var off = 84 + t*50;
      var nx=view.getFloat32(off,true), ny=view.getFloat32(off+4,true), nz=view.getFloat32(off+8,true);
      for (var v=0; v<3; v++) {{
        var vo = off+12+v*12;
        positions.push(view.getFloat32(vo,true), view.getFloat32(vo+4,true), view.getFloat32(vo+8,true));
        normals.push(nx,ny,nz);
      }}
    }}

    var allPos = new Float32Array(positions);
    var allNrm = new Float32Array(normals);

    // Build face-group index lookup: face_index → group_index
    var faceToGroup = new Int32Array(numTri).fill(-1);
    for (var g=0; g<FACE_GROUPS.length; g++) {{
      var fi = FACE_GROUPS[g].face_indices;
      for (var k=0; k<fi.length; k++) faceToGroup[fi[k]] = g;
    }}

    // Base mesh (grey, non-group faces)
    var baseGeo = new THREE.BufferGeometry();
    var basePosArr = [], baseNrmArr = [];
    for (var t=0; t<numTri; t++) {{
      if (faceToGroup[t] !== -1) continue;
      var o3 = t*9;
      for (var i=0; i<9; i++) {{ basePosArr.push(allPos[o3+i]); baseNrmArr.push(allNrm[Math.floor(o3/3)*3 + i%3]); }}
    }}
    if (basePosArr.length > 0) {{
      baseGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(basePosArr), 3));
      baseGeo.setAttribute('normal',   new THREE.BufferAttribute(new Float32Array(baseNrmArr), 3));
      scene.add(new THREE.Mesh(baseGeo, new THREE.MeshStandardMaterial({{color:0x888888, side:THREE.DoubleSide}})));
    }}

    // Group meshes
    var COLORS = {colors_json};
    var groupMeshes = [];
    for (var g=0; g<FACE_GROUPS.length; g++) {{
      var fi = FACE_GROUPS[g].face_indices;
      var gPosArr=[],gNrmArr=[];
      for (var k=0; k<fi.length; k++) {{
        var t=fi[k], o3=t*9;
        for (var i=0; i<9; i++) {{ gPosArr.push(allPos[o3+i]); gNrmArr.push(allNrm[Math.floor(o3/3)*3+i%3]); }}
      }}
      var geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(gPosArr),3));
      geo.setAttribute('normal',   new THREE.BufferAttribute(new Float32Array(gNrmArr),3));
      var mat = new THREE.MeshStandardMaterial({{
        color: new THREE.Color(COLORS[g % COLORS.length]),
        side: THREE.DoubleSide,
        transparent: true, opacity: 0.85
      }});
      var mesh3 = new THREE.Mesh(geo, mat);
      mesh3.userData.groupIndex = g;
      mesh3.userData.originalOpacity = 0.85;
      scene.add(mesh3);
      groupMeshes.push(mesh3);
    }}

    // Compute bounding sphere for camera positioning
    var tmpGeo = new THREE.BufferGeometry();
    tmpGeo.setAttribute('position', new THREE.BufferAttribute(allPos, 3));
    tmpGeo.computeBoundingSphere();
    var center = tmpGeo.boundingSphere.center;
    var radius = tmpGeo.boundingSphere.radius;
    var pivot = new THREE.Group();
    pivot.position.copy(center.negate());
    scene.add(pivot);
    // Move all meshes under pivot
    scene.children.filter(function(c){{return c instanceof THREE.Mesh || c instanceof THREE.Group;}}).forEach(function(c){{pivot.add(c);}});
    camera.position.set(0, 0, radius * 3);
    camera.lookAt(0,0,0);

    // Legend
    var legendHtml = '<b>Плоские грани:</b><br>';
    for (var g=0; g<FACE_GROUPS.length; g++) {{
      legendHtml += '<span style="display:inline-block;width:12px;height:12px;background:' + COLORS[g%COLORS.length] + ';margin-right:5px;border-radius:2px;vertical-align:middle;"></span>' +
        FACE_GROUPS[g].label + '<br>';
    }}
    legendEl.innerHTML = legendHtml;

    // Raycaster for click
    var raycaster = new THREE.Raycaster();
    var mouse     = new THREE.Vector2();
    canvas.addEventListener('click', function(e) {{
      var rect = canvas.getBoundingClientRect();
      mouse.x =  ((e.clientX - rect.left)  / rect.width)  * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      var hits = raycaster.intersectObjects(groupMeshes);
      if (hits.length > 0) {{
        var mesh3 = hits[0].object;
        var gi = mesh3.userData.groupIndex;
        var fg = FACE_GROUPS[gi];
        infoEl.textContent = '✓ Выбрана: ' + fg.label;
        // Highlight selected, dim others
        groupMeshes.forEach(function(m,i) {{
          m.material.opacity = (i===gi) ? 1.0 : 0.35;
          m.material.emissive = (i===gi) ? new THREE.Color(0x224422) : new THREE.Color(0x000000);
        }});
        // Communicate to Gradio via hidden textbox
        var payload = JSON.stringify({{group_index: gi, normal: fg.normal}});
        var inputEl = document.querySelector('#surface_face_input_{uid} input, #surface_face_input_{uid} textarea');
        if (!inputEl) inputEl = document.querySelector('[elem_id="surface_face_input_{uid}"] input');
        if (inputEl) {{
          inputEl.value = payload;
          inputEl.dispatchEvent(new Event('input', {{bubbles:true}}));
          inputEl.dispatchEvent(new Event('change', {{bubbles:true}}));
        }}
      }}
    }});

    // Resize
    function onResize() {{
      var w = canvas.clientWidth, h = canvas.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w/h; camera.updateProjectionMatrix();
    }}
    onResize();
    window.addEventListener('resize', onResize);

    // Animate
    function animate() {{
      requestAnimationFrame(animate);
      pivot.rotation.x = rotX;
      pivot.rotation.y = rotY;
      camera.position.setLength(radius * 3 * zoom);
      renderer.render(scene, camera);
    }}
    animate();
  }}
}})();
</script>
"""


def create_interactive_viewer(
    stl_path: str,
    face_groups: list,  # List[FlatFaceGroup]
    uid: str = "main",
) -> str:
    """
    Generate an HTML string with an embedded Three.js viewer.

    The viewer renders the STL, highlights flat face groups in distinct colours,
    and on click communicates the selected face normal back to Gradio via a
    hidden textbox with elem_id="surface_face_input_{uid}".

    Args:
        stl_path: absolute path to the STL file (binary format preferred)
        face_groups: list of FlatFaceGroup objects from surface_on_bed.detect_flat_faces
        uid: unique suffix for DOM element IDs (avoid conflicts on Gradio re-renders)

    Returns:
        HTML string suitable for gr.HTML(value=...).
    """
    if not os.path.exists(stl_path):
        return "<p style='color:red'>STL файл не найден: " + stl_path + "</p>"

    # Encode STL as base64
    with open(stl_path, "rb") as f:
        raw = f.read()

    # Convert ASCII STL to binary if needed (trimesh handles this better)
    if raw[:5] == b"solid" and b"endsolid" in raw:
        try:
            import trimesh
            mesh = trimesh.load(stl_path, force="mesh")
            raw = mesh.export(file_type="stl")
        except Exception:
            pass  # keep original bytes

    stl_b64 = base64.b64encode(raw).decode("ascii")

    # Serialize face groups for JS
    groups_data = []
    for fg in face_groups:
        groups_data.append({
            "group_index": int(fg.group_index),
            "normal": [round(float(x), 6) for x in fg.normal],
            "area": round(float(fg.area), 2),
            "label": fg.label,
            "face_indices": [int(i) for i in fg.face_indices],
        })

    face_groups_json = json.dumps(groups_data)
    colors_json = json.dumps(_FACE_COLORS)

    html = _VIEWER_TEMPLATE.format(
        uid=uid,
        stl_b64=stl_b64,
        face_groups_json=face_groups_json,
        colors_json=colors_json,
    )
    return html
