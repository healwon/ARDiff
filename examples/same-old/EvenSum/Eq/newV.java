public class newV {
    // loop over how many even numbers lie below n ((n + 1) / 2 of them) and add the i-th one, 2 * i, each time
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 0; i < (n + 1) / 2; i++) {
            if (i >= 0) {
                sum = sum + i * 2;
            }
        }
        return sum;
    }
}
