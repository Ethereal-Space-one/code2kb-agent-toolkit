#include <stdio.h>
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *input = fopen(argv[1], "r");
    if (!input) return 3;
    int first = fgetc(input);
    fclose(input);
    return first == EOF ? 4 : 0;
}
