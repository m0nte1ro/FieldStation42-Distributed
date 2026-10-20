//!HOOK OUTPUT
//!BIND HOOKED
//!DESC FS42 look: retro broadcast

#define LINES 540.0     // scanlines over the picture's height
#define SCAN 0.22       // how dark the gaps between lines are
#define BLOOM 0.18
#define BLEED 0.45      // red/blue smear to the side, like composite video
#define VIGNETTE 0.18

vec4 hook() {
    vec2 pos = HOOKED_pos;
    vec2 px = HOOKED_pt;
    // a little softness: old sets never had sharp pixels
    vec3 c = HOOKED_tex(pos).rgb * 0.5
           + (HOOKED_tex(pos + vec2(px.x * 1.5, 0.0)).rgb + HOOKED_tex(pos - vec2(px.x * 1.5, 0.0)).rgb) * 0.17
           + (HOOKED_tex(pos + vec2(0.0, px.y)).rgb + HOOKED_tex(pos - vec2(0.0, px.y)).rgb) * 0.08;
    // colour bleed
    c.r = mix(c.r, HOOKED_tex(pos - vec2(px.x * 3.0, 0.0)).r, BLEED);
    c.b = mix(c.b, HOOKED_tex(pos + vec2(px.x * 2.0, 0.0)).b, BLEED * 0.6);
    // bloom: bright areas glow into their neighbours
    vec3 glow = vec3(0.0);
    for (int i = -2; i <= 2; i++)
        for (int j = -2; j <= 2; j++)
            glow += HOOKED_tex(pos + vec2(float(i), float(j)) * px * 5.0).rgb;
    glow /= 25.0;
    c += BLOOM * glow * glow;
    // scanlines, then lift the brightness they take away
    float line = sin(pos.y * LINES * 3.14159265);
    c *= 1.0 - SCAN * (1.0 - line * line);
    c *= 1.0 + SCAN * 0.6;
    // vignette
    vec2 d = pos - 0.5;
    c *= 1.0 - VIGNETTE * dot(d, d) * 2.5;
    return vec4(clamp(c, 0.0, 1.0), 1.0);
}
