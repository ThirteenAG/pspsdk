/* The SDK already collects .ctors; expose its bounds without replacing it. */
__plugin_ctors_start = ADDR(.ctors);
__plugin_ctors_end = ADDR(.ctors) + SIZEOF(.ctors);
