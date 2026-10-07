#include <pspkernel.h>
#include <stdint.h>

/* Minimal PRXs have no libc startup or system heap. C++ constructors still
 * need to run, and owning hooks need bounded destructor registration. */
typedef void (*initializer)(void);
extern initializer __preinit_array_start[], __preinit_array_end[];
extern initializer __init_array_start[], __init_array_end[];
extern initializer __plugin_ctors_start[], __plugin_ctors_end[];
extern int plugin_module_start(SceSize, void*);

void* __dso_handle = &__dso_handle;
struct destructor { void (*function)(void*); void* argument; void* owner; };
static struct destructor destructors[128];
static unsigned destructor_count;
static int started, registration_failed;

int __cxa_atexit(void (*function)(void*), void* argument, void* owner)
{
    if (!function || destructor_count == sizeof(destructors) / sizeof(destructors[0])) {
        registration_failed = 1;
        return -1;
    }
    destructors[destructor_count++] = (struct destructor){function, argument, owner};
    return 0;
}

void __cxa_finalize(void* owner)
{
    unsigned i = destructor_count;
    while (i) {
        struct destructor entry = destructors[--i];
        if (entry.function && (!owner || entry.owner == owner)) {
            /* Clear first: a destructor may recursively finalize its owner. */
            destructors[i].function = 0;
            entry.function(entry.argument);
        }
    }
    while (destructor_count && !destructors[destructor_count - 1].function) --destructor_count;
}

int module_start(SceSize size, void* arguments)
{
    initializer* entry;
    if (started) return -1;
    started = 1;
    for (entry = __preinit_array_start; entry != __preinit_array_end; ++entry) if (*entry) (*entry)();
    for (entry = __init_array_start; entry != __init_array_end; ++entry) if (*entry) (*entry)();
    /* GCC's legacy .ctors list runs backwards; skip its optional sentinels. */
    for (entry = __plugin_ctors_end; entry != __plugin_ctors_start;) {
        initializer function = *--entry;
        if (function && (uintptr_t)function != UINT32_MAX) function();
    }
    if (registration_failed) { __cxa_finalize(0); return -1; }
    return plugin_module_start(size, arguments);
}
