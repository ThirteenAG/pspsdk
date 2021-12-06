#include <objc/Object.h>

@interface Greeter:Object
{
 /* This is left empty on purpose:
  ** Normally instance variables would be declared here,
  ** but these are not used in our example.
  */
}

- (void)greet;

@end


#include <pspkernel.h>
#include <pspdebug.h>
#include <pspctrl.h>

/* Define printf, just to make typing easier */
#define printf  pspDebugScreenPrintf

@implementation Greeter

- (void)greet
{
	printf("Hello, World from Obj-C!\n");
}

@end

/* Define the module info section */
PSP_MODULE_INFO("template", 0, 1, 1);

/* Define the main thread's attribute value (optional) */
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);

int main(void)
{
	/* Non Objective-C code to allow the app to end */
	pspDebugScreenInit();
	SceCtrlData pad;
	
	/* Objective-C code */
	id myGreeter;
	myGreeter=[Greeter new];

	[myGreeter greet];
	[myGreeter free];

	printf("\nPress X to quit.\n");
	for (;;)
	{
		sceCtrlReadBufferPositive(&pad, 1);
		if (pad.Buttons & PSP_CTRL_CROSS)
			break;
	}
	sceKernelExitGame();
	
	return 0;
}

