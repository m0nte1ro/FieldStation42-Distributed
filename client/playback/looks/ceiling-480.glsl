//!HOOK MAIN
//!BIND HOOKED
//!DESC FS42 resolution ceiling: 480 lines (NTSC)
//!WHEN HOOKED.h 480 >
//!WIDTH HOOKED.w 480 * HOOKED.h /
//!HEIGHT 480

// a 2x2 box average over the source pixels each new pixel covers: no shimmering on fine detail
vec4 hook() {
    vec2 d = HOOKED_pt * (HOOKED_size / target_size) * 0.25;
    return (HOOKED_tex(HOOKED_pos + vec2(-d.x, -d.y)) + HOOKED_tex(HOOKED_pos + vec2(d.x, -d.y)) +
            HOOKED_tex(HOOKED_pos + vec2(-d.x, d.y)) + HOOKED_tex(HOOKED_pos + d)) * 0.25;
}
