public class newV {
    // fast: loop-invariant price * rate computed once before the loop
    public static double snippet(int price, int rate, int n) {
        int i = 0;
        int unit = price * rate;
        int total = 0;
        for (i = 0; i < n; i++) {
            total = total + unit + i;
        }
        return total;
    }
}
