/* =========================================================================
   COPILOT — auth-screen 3D robot.
   Built from Three.js primitives (no external model), styled to match the
   site's ink / brass / parchment "consulting dossier" theme rather than a
   generic neon-AI look. Exposes window.RobotApp.setMode(mode, seconds) so
   app.js can trigger reactions from real auth events (focus, success, error).
   Modes: idle | attentive | coverEyes | celebrate | confused | thumbsUp
   ========================================================================= */
window.RobotApp = (function(){
  const holder = document.querySelector('.robot-holder');
  const canvas = document.getElementById('robot-canvas');
  if(!holder || !canvas || typeof THREE === 'undefined'){
    return { setMode(){} }; // fail quietly if three.js didn't load
  }
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, holder.clientWidth/Math.max(holder.clientHeight,1), 0.1, 100);
  camera.position.set(0, 0.35, 6.6);

  const renderer = new THREE.WebGLRenderer({ canvas, alpha:true, antialias:true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(holder.clientWidth, holder.clientHeight);

  // ---- Lighting: warm brass key + cool ink rim, matching the dossier theme ----
  scene.add(new THREE.AmbientLight(0x8f8570, 0.55));
  const keyLight = new THREE.PointLight(0xd9a94f, 2.0, 20);
  keyLight.position.set(2.4, 3, 4);
  scene.add(keyLight);
  const rimLight = new THREE.PointLight(0x3a4a6b, 1.4, 20);
  rimLight.position.set(-3, -1, -3);
  scene.add(rimLight);
  const fill = new THREE.DirectionalLight(0xf6f3ec, 0.35);
  fill.position.set(0,4,5);
  scene.add(fill);

  // ---- Materials: charcoal-ink shell, brass trim, parchment dial, amber glow ----
  const bodyMat = new THREE.MeshStandardMaterial({ color:0x232830, roughness:0.4, metalness:0.35 });
  const bodyMatDark = new THREE.MeshStandardMaterial({ color:0x14171c, roughness:0.45, metalness:0.3 });
  const buttonMat = new THREE.MeshStandardMaterial({ color:0xa9843f, emissive:0x6b5326, emissiveIntensity:0.5, roughness:0.35, metalness:0.6 });
  const socketMat = new THREE.MeshStandardMaterial({ color:0x14171c, roughness:0.5, metalness:0.3 });
  const dialMat = new THREE.MeshStandardMaterial({ color:0xf6f3ec, roughness:0.35, metalness:0.05 });
  const glowMat = new THREE.MeshStandardMaterial({ color:0xd9a94f, emissive:0xd9a94f, emissiveIntensity:2.0, roughness:0.3 });

  const robot = new THREE.Group();
  scene.add(robot);

  // ---- Rounded-cube body (box + corner fillet spheres — this three.js
  // build has no RoundedBoxGeometry/CapsuleGeometry) ----
  const bodyGroup = new THREE.Group();
  robot.add(bodyGroup);

  const HALF = 0.72;
  const FILLET = 0.22;

  bodyGroup.add(new THREE.Mesh(new THREE.BoxGeometry(HALF*2, HALF*2, HALF*2), bodyMat));

  const filletGeo = new THREE.SphereGeometry(FILLET, 16, 16);
  [-1,1].forEach(sx=>[-1,1].forEach(sy=>[-1,1].forEach(sz=>{
    const c = new THREE.Mesh(filletGeo, bodyMat);
    c.position.set(sx*HALF, sy*HALF, sz*HALF);
    bodyGroup.add(c);
  })));

  const baseDisc = new THREE.Mesh(new THREE.CylinderGeometry(0.82,0.82,0.06,32), bodyMatDark);
  baseDisc.position.y = -HALF - 0.2;
  bodyGroup.add(baseDisc);

  // Top brass button
  const socket = new THREE.Mesh(new THREE.BoxGeometry(0.44,0.04,0.44), socketMat);
  socket.position.set(0, HALF+0.02, 0);
  bodyGroup.add(socket);
  const button = new THREE.Mesh(new THREE.BoxGeometry(0.32,0.15,0.32), buttonMat);
  button.position.set(0, HALF+0.11, 0);
  bodyGroup.add(button);

  // Three indicator lights on the front face
  const dotGeo = new THREE.SphereGeometry(0.055, 14, 14);
  const dots = [0.3, 0.02, -0.26].map(y=>{
    const d = new THREE.Mesh(dotGeo, glowMat);
    d.position.set(HALF-0.05, y, HALF*0.55);
    bodyGroup.add(d);
    return d;
  });

  // Rotating side dial
  const dialGroup = new THREE.Group();
  dialGroup.position.set(-HALF-0.01, 0.05, 0);
  bodyGroup.add(dialGroup);
  const dial = new THREE.Mesh(new THREE.CylinderGeometry(0.28,0.28,0.045,32), dialMat);
  dial.rotation.z = Math.PI/2;
  dialGroup.add(dial);
  const dialPointer = new THREE.Mesh(new THREE.BoxGeometry(0.025,0.18,0.02), socketMat);
  dialPointer.position.set(-0.025, 0.07, 0);
  dialGroup.add(dialPointer);

  // Friendly smile arc, front face
  const mouth = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.015, 8, 24, Math.PI*0.85), glowMat);
  mouth.rotation.z = Math.PI*1.075;
  mouth.rotation.y = Math.PI/2;
  mouth.position.set(HALF*0.55, -0.4, 0);
  bodyGroup.add(mouth);

  robot.scale.set(1.5,1.5,1.5);
  robot.position.y = -0.1;
  robot.rotation.y = 0.5;

  /* -------- animation state -------- */
  const clock = new THREE.Clock();
  let mouseX = 0, mouseY = 0;
  let targetRotY = 0, targetRotX = 0;
  let blinkTimer = 2 + Math.random()*3;
  let mode = 'idle';
  let modeTimer = 0;

  window.addEventListener('mousemove', (e)=>{
    mouseX = (e.clientX / window.innerWidth) * 2 - 1;
    mouseY = (e.clientY / window.innerHeight) * 2 - 1;
  });

  function setMode(m, duration){
    mode = m;
    modeTimer = duration || 1.4;
  }

  function animate(){
    requestAnimationFrame(animate);
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;

    if(!reduceMotion){
      robot.position.y = -0.1 + Math.sin(t*1.1)*0.06;
      bodyGroup.scale.setScalar(1 + Math.sin(t*1.8)*0.018);
    }

    targetRotY += (0.5 + mouseX*0.35 - targetRotY)*0.06;
    targetRotX += (-mouseY*0.15 - targetRotX)*0.06;

    let lookY = targetRotX;
    let dotGlow = 2.0;
    let dialSpeed = 0.35;
    let buttonY = HALF+0.11;

    if(mode === 'attentive'){
      dotGlow = 3.1; dialSpeed = 1.4;
    } else if(mode === 'coverEyes'){
      lookY = -0.32; dotGlow = 0.4; dialSpeed = 0.05;
    } else if(mode === 'celebrate'){
      robot.position.y += Math.abs(Math.sin(t*11))*0.15;
      robot.rotation.y += Math.sin(t*10)*0.1;
      buttonY = HALF+0.11 + Math.abs(Math.sin(t*11))*0.08;
      dotGlow = 2.2 + Math.sin(t*20)*1.2;
      dialSpeed = 2.6;
    } else if(mode === 'confused'){
      targetRotY += Math.sin(t*20)*0.16;
      dotGlow = 1.0 + Math.random()*1.4;
    } else if(mode === 'thumbsUp'){
      robot.rotation.y += dt*5.5;
      dotGlow = 2.8;
      buttonY = HALF+0.11 + Math.sin(t*8)*0.045;
    }

    robot.rotation.y += (targetRotY - robot.rotation.y)*0.12;
    bodyGroup.rotation.x += (lookY - bodyGroup.rotation.x)*0.12;
    button.position.y += (buttonY - button.position.y)*0.25;
    dialGroup.rotation.x += dialSpeed*dt;

    blinkTimer -= dt;
    let blink = 1;
    if(blinkTimer < 0.12) blink = Math.max(0.15, blinkTimer/0.12);
    if(blinkTimer < 0){ blinkTimer = 2.4 + Math.random()*3; }
    glowMat.emissiveIntensity = dotGlow * blink;

    if(modeTimer > 0){
      modeTimer -= dt;
      if(modeTimer <= 0 && mode !== 'idle'){ mode = 'idle'; }
    }

    renderer.render(scene, camera);
  }
  animate();

  function handleResize(){
    const w = holder.clientWidth, h = holder.clientHeight;
    if(w===0||h===0) return;
    camera.aspect = w/h; camera.updateProjectionMatrix();
    renderer.setSize(w,h);
  }
  window.addEventListener('resize', handleResize);
  if(window.ResizeObserver){ new ResizeObserver(handleResize).observe(holder); }

  return { setMode };
})();
