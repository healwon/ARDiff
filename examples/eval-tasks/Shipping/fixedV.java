public class fixedV {
    // reference fix: free from 80 inclusive, and a free order still pays the express part
    public static double snippet(int weight, int total, int express) {
        int base = 5;
        int extra = 0;
        int rush = 0;
        int fee = 0;
        if (weight > 10) {
            extra = weight / 2 - 5;
        }
        if (express == 1) {
            rush = 7;
        }
        fee = base + extra + rush;
        if (total >= 80) {
            fee = rush;
        }
        return fee;
    }
}
