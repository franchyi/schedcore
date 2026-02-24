#include <stdio.h>
#include <math.h>

int main() {
    double sum = 0;
    int n = 210000000;
    while (n--) {
        sum += sin(n * 0.001) * cos(n * 0.001);
    }
    printf("Short: %f\n", sum);
    return 0;
}