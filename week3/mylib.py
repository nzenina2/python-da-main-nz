def myprint(s):
    print(f"Hello, {s}!")

def myprint2(s):
    for c in s:
        print(c)

if __name__ == "__main__":
    print("mylib is started as a program")
    myprint("test")
