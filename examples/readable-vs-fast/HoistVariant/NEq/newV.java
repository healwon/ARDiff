public class newV {
    // "hoisted" price * i out of the loop, but it changes every iteration
    public static double snippet(int price, int n) {
        int i = 0;
        int step = price * i;
        int total = 0;
        for (i = 0; i < n; i++) {
            total = total + step;
        }
        return total;
    }
}
