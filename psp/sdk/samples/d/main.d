// imports
//
extern (C) void pspDebugScreenInit();
extern (C) void pspDebugScreenPrintf(char*,...);
extern (C) int SetupCallbacks();
extern (C) int sceKernelSleepThread();

import std.string;

class HelloPsp
{
public:
	void sayHello()
	{
		pspDebugScreenPrintf(toStringz(m_msg));
	}
	char[] m_msg = "Hello D on Psp\n";
}

int main()
{
	SetupCallbacks();

	pspDebugScreenInit();
	
	auto hello = new HelloPsp();
	hello.sayHello();

	sceKernelSleepThread();
	return 0;
}
