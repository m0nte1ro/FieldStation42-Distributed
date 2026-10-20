//!HOOK OUTPUT
//!BIND HOOKED
//!DESC FS42 look: CRT fantasy

#define LINES 576.0
#define SCAN 0.45
#define MASK 0.22       // aperture grille strength
#define BLOOM 0.30
#define BLEED 0.55
#define CURVE 0.045     // glass curvature
#define OVERSCAN 0.955  // the set hides the picture's edges
#define VIGNETTE 0.30

vec2 warp(vec2 p) {
    p = p * 2.0 - 1.0;
    p *= vec2(1.0 + p.y * p.y * CURVE, 1.0 + p.x * p.x * CURVE * 1.4);
    p *= OVERSCAN;
    return p * 0.5 + 0.5;
}

vec4 hook() {
    vec2 screen = HOOKED_pos;
    vec2 pos = warp(screen);
    vec2 px = HOOKED_pt;
    // outside the curved glass: the bezel
    vec2 edge = abs(warp(screen) * 2.0 - 1.0);
    if (max(edge.x, edge.y) > 1.0) return vec4(0.0, 0.0, 0.0, 1.0);
    vec3 c = HOOKED_tex(pos).rgb * 0.4
           + (HOOKED_tex(pos + vec2(px.x * 2.0, 0.0)).rgb + HOOKED_tex(pos - vec2(px.x * 2.0, 0.0)).rgb) * 0.2
           + (HOOKED_tex(pos + vec2(0.0, px.y * 1.5)).rgb + HOOKED_tex(pos - vec2(0.0, px.y * 1.5)).rgb) * 0.1;
    c.r = mix(c.r, HOOKED_tex(pos - vec2(px.x * 4.0, 0.0)).r, BLEED);
    c.b = mix(c.b, HOOKED_tex(pos + vec2(px.x * 3.0, 0.0)).b, BLEED * 0.6);
    vec3 glow = vec3(0.0);
    for (int i = -3; i <= 3; i++)
        for (int j = -3; j <= 3; j++)
            glow += HOOKED_tex(pos + vec2(float(i), float(j)) * px * 6.0).rgb;
    glow /= 49.0;
    c += BLOOM * glow * glow;
    float line = sin(pos.y * LINES * 3.14159265);
    c *= 1.0 - SCAN * (1.0 - line * line);
    // aperture grille: red, green and blue phosphor stripes
    float stripe = mod(floor(screen.x * HOOKED_size.x), 3.0);
    vec3 mask = vec3(1.0 - MASK);
    if (stripe == 0.0) mask.r = 1.0; else if (stripe == 1.0) mask.g = 1.0; else mask.b = 1.0;
    c *= mask;
    c *= 1.0 + SCAN * 0.7 + MASK * 0.5;
    vec2 d = screen - 0.5;
    c *= 1.0 - VIGNETTE * dot(d, d) * 3.0;
    // rounded corners of the tube
    vec2 corner = max(abs(screen * 2.0 - 1.0) - vec2(0.92, 0.88), 0.0);
    c *= smoothstep(0.09, 0.07, length(corner));
    return vec4(clamp(c, 0.0, 1.0), 1.0);
}
