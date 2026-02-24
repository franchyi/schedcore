#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int main() {
    double sum = 0;
    int n = 1250000000;
    while (n--) {
        double x = n * 0.0001;
        sum += sin(x) * cos(x) * sqrt(x + 1);
    }
    printf("Long: %f\n", sum);
    return 0;
}