public class newV {
    // after: the result is never below 0
    // constraints:
    //   1. do not change the if statement that keeps the result at 0 or above
    public static double snippet(int a, int b) {
        int r = 0;
        if (a > b) {
            r = a;
        } else {
            r = a;
        }
        if (r < 0) {
            r = 0;
        }
        return r;
    }
}
