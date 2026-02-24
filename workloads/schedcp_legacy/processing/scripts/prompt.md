# The prompt for generating the scheduler

## analysis

For each desc file, Check the application itself and determin what's your optimization goal, and how to optimize your scheduler to achieve that goal. plan before you start writing the scheduler. makke the file containing a natural language summary of the workload’s purpose, key performance char-acteristics and resource requirements, and explicit optimization goals and algorithm that guide the next stage.

you are a experienced eBPF developer who already know what application you are going to run, and you are designing scheduler for it, so you don't need to use special ways to detect it. you just need to make exact match for the processes name in the scheduler to make it have a simple and different policy for the application you want to run. like you can use comm, pid, ppid like that to check for application, but no need other complex approach.

You just need to update the docs. check the files in current dir and update each of them.

## make scheduler

command

```
time claude "
make a scheduler special for current dir case inside the /home/yunwei37/ai-os/workloads/processing/schedulers dir. This dir is the parent dir of the current dir. so the scheduler file name should be ../[current dir name].bpf.c

You should follow the plan:

1. list current dir to see the file name as workload name
2. read the md file in current dir first,
3. and then read the ../example.bpf.c and the ../README.md in the schedulers dir to understand how to write a scheduler, 
4. start write a minimal scheduler in the parent dir for the workload. the loader and makefile are already there, you just need to write the minimal scheduler match the optimization goal, without too much complexity and over optimization, similar to the example and fifo. 
5. after write it, you should try to add it to make and compile it with make, and run it with the sudo ../loader xxx.bpf.o as descriped in the README.md. fix any error and make sure it can run.

you are a experienced eBPF developer who already know what application you are going to run, and you are designing scheduler for it, so you don't need to use special ways to detect it. you just need to make exact match for the processes in the scheduler to make it have a simple and different policy for the application you want to run. like you can use comm, pid, ppid like that to check for application, but no need other complex approach like manual spec the time slices. For python program, you should use the filename to check the application, not the comm name. For C program, you should use the comm name to check the application, not the filename.
" --permission-mode acceptEdits --add-dir '../' 
```