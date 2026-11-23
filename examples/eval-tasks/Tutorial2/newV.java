public class newV {
    // after: the result is never above 50
    // constraints:
    //   1. do not change the if statement that keeps the result at 50 or below
    public static double snippet(int a, int b) {
        int r = 0;
        if (a < b) {
            r = a;
        } else {
            r = a;
        }
        if (r > 50) {
            r = 50;
        }
        return r;
    }
}
