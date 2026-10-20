//!HOOK MAIN
//!BIND HOOKED
//!DESC FS42 resolution ceiling: 576 lines (PAL)
//!WHEN HOOKED.h 576 >
//!WIDTH HOOKED.w 576 * HOOKED.h /
//!HEIGHT 576

// a 2x2 box average over the source pixels each new pixel covers: no shimmering on fine detail
vec4 hook() {
    vec2 d = HOOKED_pt * (HOOKED_size / target_size) * 0.25;
    return (HOOKED_tex(HOOKED_pos + vec2(-d.x, -d.y)) + HOOKED_tex(HOOKED_pos + vec2(d.x, -d.y)) +
            HOOKED_tex(HOOKED_pos + vec2(-d.x, d.y)) + HOOKED_tex(HOOKED_pos + d)) * 0.25;
}
